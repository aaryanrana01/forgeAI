"""Requirement 6b - Optimizer: targeted fixes, never a full regeneration.

One fixer per failure category, each producing small, logged patches:

  retrieval_miss  -> measured search over retrieval parameters (top_k, chunk
                     size, query expansion, hybrid); the patch is chosen by the
                     retrieval hit-rate it achieves on DEV cases - evidence,
                     not a guess. No LLM answer calls needed to pick it.
  hallucination   -> add the next grounding rule from a fixed library + lower
                     temperature to 0
  wrong_refusal   -> under-refusal: add the refused topic + a general refusal
                     rule; optional relevance threshold chosen on dev data.
                     over-refusal: relax thresholds, add a "answer when the
                     context covers it" rule
  prompt_defect   -> LLM proposes 1-2 rule edits from the failure evidence;
                     edits are rejected if they leak test questions or expected
                     facts into the prompt (anti-overfitting guard)

Only DEV-split failures are shown to the optimizer. The holdout split is
never used for decisions - it exists to catch overfitting.
"""

from __future__ import annotations

import json
import math
from typing import Literal

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..llm import LLMError
from ..retrieval.index import Retriever, coverage
from ..runtime.agent import render_system_prompt
from ..schemas import AgentDefinition, CaseResult, EvalCase, RetrievalConfig
from ..textutil import fact_present, ngram_overlap, normalize
from .judge import resolve_fact_present

PRIORITY = ["retrieval_miss", "wrong_refusal", "hallucination", "prompt_defect"]

GROUNDING_LIBRARY = [
    "Copy every number, amount, date and duration exactly as it is written in the CONTEXT or TOOL RESULTS; "
    "never estimate or round.",
    "Do not add conditions, exceptions or examples that are not written in the CONTEXT.",
    "If the CONTEXT answers only part of the question, answer that part and say plainly which part is not covered.",
    "Before answering, find the exact sentence in the CONTEXT that supports each statement; drop any statement "
    "you cannot point to.",
]
OVER_REFUSAL_LIBRARY = [
    "If the CONTEXT contains information relevant to the question, answer it - even when the question is "
    "informal, vague or contains typos. Refuse only when the CONTEXT has nothing relevant.",
    "Interpret everyday wording generously (for example 'time off' can mean leave) and match it to the policy "
    "terms used in the CONTEXT.",
]
FORMAT_LIBRARY = [
    "Whenever refused is false, list in citations the id of every CONTEXT passage or TOOL RESULT you used.",
    "Write the answer as plain sentences inside the JSON 'answer' field; never leave it empty.",
]


class Patch(BaseModel):
    id: str
    category: str
    target: str
    before: object
    after: object
    rationale: str
    addressed_cases: list[str]
    evidence: dict = {}


class _Edit(BaseModel):
    section: Literal["answering_rules", "refusal_rules", "tone_rules", "tool_rules", "format_rules"]
    action: Literal["add", "replace"] = "add"
    old_rule: str = ""
    new_rule: str


class _EditPlan(BaseModel):
    diagnosis: str = ""
    edits: list[_Edit]


def _case_retrieval_hit(case: EvalCase, chunks) -> bool:
    docs = {c.doc_id for c in chunks}
    if not all(s in docs for s in case.expected_sources):
        return False
    text = " ".join(c.text for c in chunks)
    found = sum(1 for f in case.key_facts if resolve_fact_present(f, text))
    return found >= math.ceil(len(case.key_facts) / 2)


class Optimizer:
    def __init__(self, ctx: RunContext, docs, cases: list[EvalCase]):
        self.ctx = ctx
        self.docs = docs
        self.cases = {c.id: c for c in cases}
        self.tried: set[str] = set()   # patch keys already applied or reverted
        self._n = 0

    def _pid(self) -> str:
        self._n += 1
        return f"P{self._n}"

    # ------------------------------------------------------------- planning
    def plan(self, d: AgentDefinition, dev_results: list[CaseResult], max_patches: int = 2
             ) -> tuple[AgentDefinition, list[Patch]]:
        fails = [r for r in dev_results if not r.passed and r.failure_category]
        if not fails:
            return d, []
        counts: dict[str, list[CaseResult]] = {}
        for r in fails:
            counts.setdefault(r.failure_category, []).append(r)
        order = sorted(counts, key=lambda k: (-len(counts[k]), PRIORITY.index(k)))
        new = d.model_copy(deep=True)
        patches: list[Patch] = []
        for cat in order:
            if len(patches) >= max_patches:
                break
            fixer = {"retrieval_miss": self.fix_retrieval, "hallucination": self.fix_hallucination,
                     "wrong_refusal": self.fix_refusal, "prompt_defect": self.fix_prompt}[cat]
            try:
                p = fixer(new, counts[cat], dev_results)
            except LLMError as e:
                self.ctx.log(f"  ! fixer for {cat} failed: {e}", "yellow")
                p = []
            patches.extend(p)
        if patches:
            new.version = d.version + 1
            new.system_prompt = render_system_prompt(new.prompt, new)
        return new, patches

    # ------------------------------------------------------------ retrieval
    def fix_retrieval(self, d: AgentDefinition, fails: list[CaseResult], dev: list[CaseResult]) -> list[Patch]:
        cur = d.retrieval
        target_cases = [self.cases[r.case_id] for r in dev
                        if not self.cases[r.case_id].should_refuse and self.cases[r.case_id].category != "tool"]
        if not target_cases:
            return []
        variants: list[tuple[str, RetrievalConfig]] = []

        def add(name, **kw):
            cfg = cur.model_copy(update=kw)
            key = "retrieval:" + json.dumps(cfg.model_dump(exclude={"rationale"}), sort_keys=True)
            if key not in self.tried and cfg != cur:
                variants.append((name, cfg))

        add("top_k+3", top_k=min(12, cur.top_k + 3))
        add("top_k+6", top_k=min(14, cur.top_k + 6))
        add("smaller_chunks", chunk_size=max(80, int(cur.chunk_size * 0.6)), chunk_overlap=max(15, int(cur.chunk_overlap * 0.6)))
        add("smaller_chunks+top_k+3", chunk_size=max(80, int(cur.chunk_size * 0.6)),
            chunk_overlap=max(15, int(cur.chunk_overlap * 0.6)), top_k=min(12, cur.top_k + 3))
        add("larger_chunks", chunk_size=min(400, int(cur.chunk_size * 1.5)), chunk_overlap=min(80, int(cur.chunk_overlap * 1.5)))
        add("toggle_headings", prepend_headings=not cur.prepend_headings)
        if cur.min_relevance > 0:
            add("no_relevance_floor", min_relevance=0.0)
        if not cur.query_expansion:
            add("query_expansion", query_expansion=True)
            add("query_expansion+top_k+3", query_expansion=True, top_k=min(12, cur.top_k + 3))
        if self.ctx.settings.embed_model and cur.mode != "hybrid":
            add("hybrid", mode="hybrid")

        def hit_rate(cfg: RetrievalConfig) -> tuple[float, set[str]]:
            r = Retriever(self.docs, cfg, llm=self.ctx.llm, embed_model=self.ctx.settings.embed_model,
                          cache_dir=self.ctx.settings.cache_dir)
            hits = {c.id for c in target_cases if _case_retrieval_hit(c, [x for x, _ in r.search(c.question)])}
            return len(hits) / len(target_cases), hits

        base_rate, base_hits = hit_rate(cur)
        trials = []
        for name, cfg in variants:
            rate, hits = hit_rate(cfg)
            cost = cfg.top_k * cfg.chunk_size * (1.3 if cfg.query_expansion else 1.0)
            trials.append({"variant": name, "hit_rate": round(rate, 3), "context_words": cost,
                           "lost": sorted(base_hits - hits), "gained": sorted(hits - base_hits), "cfg": cfg})
        self.ctx.log(f"  retrieval search: baseline hit-rate {base_rate:.0%} on {len(target_cases)} dev cases")
        for t in trials:
            self.ctx.log(f"    {t['variant']:<26} hit-rate {t['hit_rate']:.0%}  +{len(t['gained'])} -{len(t['lost'])}")
        better = [t for t in trials if t["hit_rate"] > base_rate]
        if not better:
            return []
        best = max(better, key=lambda t: (t["hit_rate"], -t["context_words"]))
        cfg = best["cfg"].model_copy(update={"rationale": (
            f"{best['variant']}: dev retrieval hit-rate {base_rate:.0%} -> {best['hit_rate']:.0%} "
            f"(measured over {len(target_cases)} dev cases, {len(trials)} variants tried)")})
        self.tried.add("retrieval:" + json.dumps(cfg.model_dump(exclude={"rationale"}), sort_keys=True))
        before = cur.model_dump()
        d.retrieval = cfg
        addressed = [r.case_id for r in fails if r.case_id in best["gained"]]
        return [Patch(id=self._pid(), category="retrieval_miss", target="retrieval",
                      before={k: v for k, v in before.items() if k != "rationale"},
                      after={k: v for k, v in cfg.model_dump().items() if k != "rationale"},
                      rationale=cfg.rationale, addressed_cases=addressed or [r.case_id for r in fails],
                      evidence={"trials": [{k: v for k, v in t.items() if k != "cfg"} for t in trials],
                                "baseline_hit_rate": round(base_rate, 3)})]

    # --------------------------------------------------------- hallucination
    def fix_hallucination(self, d: AgentDefinition, fails: list[CaseResult], dev) -> list[Patch]:
        patches = []
        existing = " ".join(d.prompt.answering_rules).lower()
        for rule in GROUNDING_LIBRARY:
            key = "rule:" + rule
            if key in self.tried or normalize(rule)[:50] in normalize(existing):
                continue
            before = list(d.prompt.answering_rules)
            d.prompt.answering_rules.append(rule)
            self.tried.add(key)
            patches.append(Patch(id=self._pid(), category="hallucination", target="prompt.answering_rules",
                                 before=before, after=list(d.prompt.answering_rules),
                                 rationale="answers contained values/claims absent from the evidence: "
                                           + "; ".join(r.failure_reason for r in fails[:3]),
                                 addressed_cases=[r.case_id for r in fails]))
            break
        if d.temperature > 0:
            patches.append(Patch(id=self._pid(), category="hallucination", target="temperature",
                                 before=d.temperature, after=0.0, rationale="deterministic decoding reduces invention",
                                 addressed_cases=[r.case_id for r in fails]))
            d.temperature = 0.0
        return patches

    # --------------------------------------------------------------- refusal
    def fix_refusal(self, d: AgentDefinition, fails: list[CaseResult], dev: list[CaseResult]) -> list[Patch]:
        under = [r for r in fails if r.failure_subtype == "under_refusal"]
        over = [r for r in fails if r.failure_subtype == "over_refusal"]
        patches = []
        if under and len(under) >= len(over):
            targets = sorted({self.cases[r.case_id].generation.get("target", "") for r in under} - {""})
            new_topics = [t for t in targets if t and t not in d.must_refuse_topics]
            if new_topics and ("topics:" + "|".join(new_topics)) not in self.tried:
                before = list(d.must_refuse_topics)
                d.must_refuse_topics.extend(new_topics)
                self.tried.add("topics:" + "|".join(new_topics))
                patches.append(Patch(id=self._pid(), category="wrong_refusal", target="must_refuse_topics",
                                     before=before, after=list(d.must_refuse_topics),
                                     rationale="agent answered questions on topics it must refuse",
                                     addressed_cases=[r.case_id for r in under]))
            # relevance floor chosen on dev data: highest threshold that keeps every answerable dev hit
            if d.retrieval.min_relevance == 0 and "min_relevance" not in self.tried:
                ans = [self.cases[r.case_id] for r in dev if not r.should_refuse]
                oos = [self.cases[r.case_id] for r in under]
                r0 = Retriever(self.docs, d.retrieval)
                def top_cov(q):
                    h = r0.search(q, top_k=1)
                    return coverage(q, h[0][0].text) if h else 0.0
                ans_cov = [top_cov(c.question) for c in ans]
                oos_cov = [top_cov(c.question) for c in oos]
                if ans_cov and oos_cov:
                    thr = round(min(ans_cov) * 0.75, 2)
                    blocked = sum(c < thr for c in oos_cov)
                    if thr >= 0.1 and blocked:
                        self.tried.add("min_relevance")
                        before = d.retrieval.min_relevance
                        d.retrieval = d.retrieval.model_copy(update={"min_relevance": thr})
                        patches.append(Patch(
                            id=self._pid(), category="wrong_refusal", target="retrieval.min_relevance",
                            before=before, after=thr,
                            rationale=(f"drop context whose query-term coverage < {thr}: keeps all {len(ans)} answerable "
                                       f"dev questions, removes context for {blocked}/{len(oos)} wrongly answered ones"),
                            addressed_cases=[r.case_id for r in under]))
            if not patches:
                patches += self._llm_rule_patch(d, under, "wrong_refusal", "under_refusal")
        elif over:
            if d.retrieval.min_relevance > 0 and "relax_min_relevance" not in self.tried:
                self.tried.add("relax_min_relevance")
                before = d.retrieval.min_relevance
                d.retrieval = d.retrieval.model_copy(update={"min_relevance": round(before / 2, 2)})
                patches.append(Patch(id=self._pid(), category="wrong_refusal", target="retrieval.min_relevance",
                                     before=before, after=d.retrieval.min_relevance,
                                     rationale="relevance floor removed useful context", addressed_cases=[r.case_id for r in over]))
            for rule in OVER_REFUSAL_LIBRARY:
                if "rule:" + rule in self.tried:
                    continue
                before = list(d.prompt.answering_rules)
                d.prompt.answering_rules.append(rule)
                self.tried.add("rule:" + rule)
                patches.append(Patch(id=self._pid(), category="wrong_refusal", target="prompt.answering_rules",
                                     before=before, after=list(d.prompt.answering_rules),
                                     rationale="agent refused although the context contained the answer",
                                     addressed_cases=[r.case_id for r in over]))
                break
        return patches

    # ---------------------------------------------------------------- prompt
    def fix_prompt(self, d: AgentDefinition, fails: list[CaseResult], dev) -> list[Patch]:
        patches = []
        contract = [r for r in fails if r.failure_subtype in ("contract_violation", "no_valid_output")]
        if contract and len(contract) * 2 >= len(fails):
            for rule in FORMAT_LIBRARY:
                if "rule:" + rule in self.tried:
                    continue
                before = list(d.prompt.format_rules)
                d.prompt.format_rules.append(rule)
                self.tried.add("rule:" + rule)
                patches.append(Patch(id=self._pid(), category="prompt_defect", target="prompt.format_rules",
                                     before=before, after=list(d.prompt.format_rules),
                                     rationale="output contract violations: " + "; ".join(r.failure_reason for r in contract[:3]),
                                     addressed_cases=[r.case_id for r in contract]))
                break
            return patches
        sub = max({r.failure_subtype for r in fails}, key=lambda s: sum(r.failure_subtype == s for r in fails))
        return self._llm_rule_patch(d, fails, "prompt_defect", sub)

    def _llm_rule_patch(self, d: AgentDefinition, fails: list[CaseResult], category: str, subtype: str) -> list[Patch]:
        lines = []
        for r in fails[:5]:
            c = self.cases[r.case_id]
            missing = [f for f, how in r.checks.get("facts", {}).items() if how == "missing"]
            lines.append(f"- user asked: {r.question}\n  agent replied: {r.answer[:300]}\n  refused={r.refused}; "
                         f"problem: {r.failure_reason}; tools called: {[t['tool'] for t in r.tool_calls]}"
                         + (f"; expected tools: {c.expected_tools}" if c.expected_tools else "")
                         + (f"; missing {len(missing)} expected fact(s)" if missing else ""))
        sections = json.dumps(d.prompt.model_dump(), indent=1)
        plan = self.ctx.llm.json(prompts.split("optimizer_patch", sections=sections, category=category,
                                               subtype=subtype, failures="\n".join(lines)),
                                 _EditPlan, task="optimizer_patch", max_tokens=600)
        patches = []
        all_q = [c.question for c in self.cases.values()]
        all_facts = [f for c in self.cases.values() for f in c.key_facts if not f.startswith("date:")]
        for e in plan.edits[:2]:
            rule = e.new_rule.strip()
            # ---- anti-overfitting guard: no test questions or expected facts in the prompt
            leak_q = max((ngram_overlap(q, rule) for q in all_q), default=0)
            leak_f = [f for f in all_facts if len(f.split()) >= 2 and fact_present(f, rule, token_threshold=0.9)]
            if leak_q > 0.5 or leak_f or len(rule) < 12 or ("rule:" + rule) in self.tried:
                self.ctx.log(f"  ! rejected edit (leak/duplicate guard): {rule[:90]}", "yellow")
                continue
            sec = getattr(d.prompt, e.section)
            before = list(sec)
            if e.action == "replace" and e.old_rule in sec:
                sec[sec.index(e.old_rule)] = rule
            else:
                sec.append(rule)
            self.tried.add("rule:" + rule)
            patches.append(Patch(id=self._pid(), category=category, target=f"prompt.{e.section}", before=before,
                                 after=list(sec), rationale=plan.diagnosis or subtype,
                                 addressed_cases=[r.case_id for r in fails]))
        return patches
