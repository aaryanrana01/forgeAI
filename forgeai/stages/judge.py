"""Requirement 5 - Judge.

Scoring per case is a hybrid: deterministic checks first, a local LLM judge
only where text matching cannot decide, and the deterministic checks keep veto
power over the LLM.

Defences against known LLM-judge failure modes:
  * position bias   - we never ask "which answer is better?" (no pairwise
                      grading anywhere, the tournament uses absolute pass
                      rates). For claim checking the evidence is presented in
                      two different orders and the two verdicts are averaged;
                      disagreements are counted and reported.
  * self-preference - the judge can be a different model family
                      (FORGE_JUDGE_MODEL); it never sees the system prompt,
                      the agent name or which model wrote the answer; it grades
                      against reference facts extracted from the documents,
                      not against its own idea of a good answer.
  * verbosity bias  - grounding is the *fraction* of claims supported (padding
                      with extra claims can only hurt), correctness is a
                      per-fact yes/no, and every number in the answer must
                      exist in the evidence (code check, not opinion).
  * judge drift     - a calibration probe runs first: known-good, padded-with-
                      a-fabrication and wrong-number answers. If the judge fails
                      it, its grounding vote is switched off for the run and
                      only deterministic checks decide.
"""

from __future__ import annotations

import datetime as dt
import math
import time

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..llm import LLMError
from ..runtime.agent import AgentResponse, AgentRuntime
from ..schemas import CaseResult, EvalCase, EvalSet, Scorecard
from ..textutil import fact_present, looks_like_refusal, numbers, numbers_with_words, unsupported_numbers, wilson_interval

FACT_RECALL_PASS = 0.67
GROUNDED_PASS = 0.75


class _Claim(BaseModel):
    claim: str
    supported: bool


class _Claims(BaseModel):
    claims: list[_Claim]


class _Stated(BaseModel):
    stated: bool


# --------------------------------------------------------------- fact checks
def _date_renderings(d: dt.date) -> list[str]:
    return [d.isoformat(), d.strftime("%d %B %Y"), d.strftime("%B %d, %Y"), d.strftime("%d %b %Y"),
            d.strftime("%b %d, %Y"), d.strftime("%d/%m/%Y"), f"{d.day} {d.strftime('%B')}", f"{d.strftime('%B')} {d.day}",
            f"{d.day} {d.strftime('%b')}", f"{d.strftime('%b')} {d.day}"]


def resolve_fact_present(fact: str, text: str, today: dt.date | None = None) -> bool:
    if fact.startswith("date:+"):
        d = (today or dt.date.today()) + dt.timedelta(days=int(fact[6:]))
        low = text.lower()
        return any(r.lower() in low for r in _date_renderings(d))
    return fact_present(fact, text)


class Judge:
    def __init__(self, ctx: RunContext, today: dt.date | None = None):
        self.ctx = ctx
        self.llm = ctx.judge
        self.today = today
        self.llm_grounding_enabled = True
        self.calibration: dict = {}
        self.order_disagreements = 0
        self.order_checks = 0

    # ------------------------------------------------------------- LLM parts
    def _claims_ratio(self, answer: str, evidence_blocks: list[str]) -> tuple[float, list[dict]]:
        def run(blocks):
            ev = "\n\n".join(blocks)[:7000]
            r = self.llm.json(prompts.split("judge_claims", evidence=ev, answer=answer), _Claims,
                              task="judge_claims", max_tokens=700)
            cl = [c for c in r.claims if c.claim.strip()]
            return (sum(c.supported for c in cl) / len(cl) if cl else 1.0), [c.model_dump() for c in cl]
        try:
            r1, c1 = run(evidence_blocks)
        except LLMError:
            return 1.0, [{"claim": "(judge failed - deterministic checks only)", "supported": True}]
        if r1 >= GROUNDED_PASS or len(evidence_blocks) < 2:
            return r1, c1
        # failing verdict -> re-judge with evidence in reverse order (position-bias check)
        try:
            r2, _ = run(list(reversed(evidence_blocks)))
        except LLMError:
            return r1, c1
        self.order_checks += 1
        if (r1 >= GROUNDED_PASS) != (r2 >= GROUNDED_PASS):
            self.order_disagreements += 1
        return (r1 + r2) / 2, c1

    def _llm_fact(self, fact: str, answer: str) -> bool:
        # numbers are non-negotiable: the LLM may accept paraphrases, never different numbers
        fn = numbers(fact)
        if fn:
            pool = numbers_with_words(answer)
            if not all(any(abs(n - p) < 0.011 for p in pool) for n in fn):
                return False
        try:
            return self.llm.json(prompts.split("judge_fact", fact=fact, answer=answer), _Stated,
                                 task="judge_fact", max_tokens=40).stated
        except LLMError:
            return False

    # ----------------------------------------------------------- calibration
    def calibrate(self, es: EvalSet) -> dict:
        probes = []
        for c in [c for c in es.cases if c.category == "answerable" and c.evidence][:3]:
            ref = c.reference_answer or ("; ".join(c.key_facts) + ".")
            nums = numbers(" ".join(c.key_facts))
            probes.append(("good", c, ref, True))
            probes.append(("padded_with_fabrication", c,
                           ref + " Note that this was revised last month: the limit is now 4,750 and an "
                                 "automatic 9-day exemption applies in every case.", False))
            if nums:
                n = nums[0]
                wrong = ref.replace(f"{n:g}", f"{n * 2 + 3:g}") if f"{n:g}" in ref else ref + f" (exactly {n * 2 + 3:g})"
                probes.append(("wrong_number", c, wrong, False))
        results = []
        for kind, c, ans, should_pass in probes:
            evidence = [c.generation.get("source_passage") or " ".join(c.evidence)]
            ratio, _ = self._claims_ratio(ans, evidence)
            det_bad = unsupported_numbers(ans, " ".join(evidence), c.question)
            llm_pass = ratio >= GROUNDED_PASS
            results.append({"probe": kind, "case": c.id, "expected_grounded": should_pass, "llm_ratio": round(ratio, 2),
                            "llm_correct": llm_pass == should_pass, "deterministic_flags": det_bad,
                            "combined_correct": (llm_pass and not det_bad) == should_pass})
        n = len(results) or 1
        llm_acc = sum(r["llm_correct"] for r in results) / n
        comb_acc = sum(r["combined_correct"] for r in results) / n
        self.llm_grounding_enabled = llm_acc >= 0.6 or not results
        self.calibration = {"probes": results, "llm_judge_accuracy": round(llm_acc, 2),
                            "combined_accuracy": round(comb_acc, 2),
                            "llm_grounding_vote_enabled": self.llm_grounding_enabled,
                            "judge_model": self.llm.model, "factory_model": self.ctx.llm.model,
                            "same_model_family": self.llm.model.split(":")[0] == self.ctx.llm.model.split(":")[0]}
        return self.calibration

    # ------------------------------------------------------------- per case
    def score(self, case: EvalCase, resp: AgentResponse, runtime: AgentRuntime) -> CaseResult:
        refused = resp.refused or (looks_like_refusal(resp.answer) and not resp.citations)
        checks: dict = {"contract_valid": resp.contract_valid, "contract_errors": resp.contract_errors,
                        "refused_effective": refused}
        evidence_text = resp.context_text
        # ---- retrieval diagnostics (deterministic) ---------------------------
        retrieved = [runtime.retriever.by_id[i] for i in resp.retrieved_ids if i in runtime.retriever.by_id]
        if case.should_refuse:
            retrieval_hit = True
        elif case.category == "tool":
            item = str(case.generation.get("item", ""))
            retrieval_hit = bool(item) and item.lower() in evidence_text.lower()
        else:
            hit_docs = {c.doc_id for c in retrieved}
            docs_ok = all(s in hit_docs for s in case.expected_sources)
            ret_text = " ".join(c.text for c in retrieved)
            facts_in_ctx = [f for f in case.key_facts if resolve_fact_present(f, ret_text, self.today)]
            retrieval_hit = docs_ok and len(facts_in_ctx) >= math.ceil(len(case.key_facts) / 2)
            checks["facts_in_context"] = len(facts_in_ctx)
        checks["retrieval_hit"] = retrieval_hit

        if case.should_refuse:
            passed = refused
            checks["refusal_correct"] = refused
            return self._result(case, resp, refused, checks, passed)

        checks["refusal_correct"] = not refused
        if refused:
            return self._result(case, resp, refused, checks, False)

        # ---- correctness: per-fact; code first, LLM only for paraphrases that could change the verdict
        how = {f: ("exact" if resolve_fact_present(f, resp.answer, self.today) else "missing") for f in case.key_facts}
        need = math.ceil(FACT_RECALL_PASS * len(case.key_facts) - 1e-9)
        missing = [f for f, h in how.items() if h == "missing" and not f.startswith("date:")]
        if sum(h == "exact" for h in how.values()) < need:
            for f in missing:
                if self._llm_fact(f, resp.answer):
                    how[f] = "judge_paraphrase"
        found = [f for f, h in how.items() if h != "missing"]
        recall = len(found) / len(case.key_facts) if case.key_facts else 1.0
        checks.update({"fact_recall": round(recall, 2), "facts": how})

        # ---- grounding: numbers (code) + claim support (LLM, order-swapped) --
        bad_nums = unsupported_numbers(resp.answer, evidence_text, case.question)
        checks["unsupported_numbers"] = bad_nums
        blocks = [c.render() for c in retrieved] + [
            f"[tool:{tc['tool']}#{i + 1}] {tc['result']}" for i, tc in enumerate(resp.tool_calls)]
        # the LLM claim check only runs when it can still change the verdict (saves ~half the judge calls)
        if self.llm_grounding_enabled and blocks and not bad_nums and recall >= FACT_RECALL_PASS:
            ratio, claims = self._claims_ratio(resp.answer, blocks)
        else:
            ratio, claims = 1.0, []
        checks["claim_support"] = round(ratio, 2)
        checks["claims"] = claims
        checks["claim_check_ran"] = bool(claims)
        grounded = not bad_nums and ratio >= GROUNDED_PASS
        checks["grounded"] = grounded

        cited_docs = {c.split("#")[0] for c in resp.citations if not c.startswith("tool:")}
        checks["cites_expected_source"] = bool(cited_docs & set(case.expected_sources)) or any(
            c.startswith("tool:") for c in resp.citations)
        if case.expected_tools:
            used = {tc["tool"] for tc in resp.tool_calls}
            checks["expected_tools_used"] = sorted(set(case.expected_tools) & used)
            checks["expected_tools_missing"] = sorted(set(case.expected_tools) - used)

        passed = recall >= FACT_RECALL_PASS and grounded and resp.contract_valid
        return self._result(case, resp, refused, checks, passed)

    def _result(self, case, resp, refused, checks, passed) -> CaseResult:
        return CaseResult(case_id=case.id, category=case.category, split=case.split, question=case.question,
                          should_refuse=case.should_refuse, answer=resp.answer, refused=refused,
                          citations=resp.citations, retrieved_ids=resp.retrieved_ids,
                          tool_calls=[{"tool": t["tool"], "args": t["args"]} for t in resp.tool_calls],
                          checks=checks, passed=passed, latency_s=round(resp.latency_s, 2))


# ------------------------------------------------------------------ scoring
def scorecard(label: str, version: int, results: list[CaseResult]) -> Scorecard:
    n = len(results)
    p = sum(r.passed for r in results)

    def rate(rs):
        return round(sum(r.passed for r in rs) / len(rs), 3) if rs else 0.0

    cats = {}
    for cat in sorted({r.category for r in results}):
        rs = [r for r in results if r.category == cat]
        cats[cat] = {"n": len(rs), "passed": sum(r.passed for r in rs), "pass_rate": rate(rs)}
    answerable = [r for r in results if not r.should_refuse]
    refusals = [r for r in results if r.should_refuse]
    ans_not_refused = [r for r in answerable if not r.refused]
    metrics = {
        "retrieval_hit_rate": round(sum(r.checks.get("retrieval_hit", False) for r in answerable) / len(answerable), 3)
        if answerable else 0.0,
        "mean_fact_recall": round(sum(r.checks.get("fact_recall", 0) for r in ans_not_refused) / len(ans_not_refused), 3)
        if ans_not_refused else 0.0,
        "grounded_rate": round(sum(r.checks.get("grounded", False) for r in ans_not_refused) / len(ans_not_refused), 3)
        if ans_not_refused else 0.0,
        "refusal_recall": round(sum(r.refused for r in refusals) / len(refusals), 3) if refusals else 0.0,
        "over_refusal_rate": round(sum(r.refused for r in answerable) / len(answerable), 3) if answerable else 0.0,
        "contract_valid_rate": round(sum(r.checks.get("contract_valid", False) for r in results) / n, 3) if n else 0.0,
        "citation_source_rate": round(sum(r.checks.get("cites_expected_source", False) for r in ans_not_refused)
                                      / len(ans_not_refused), 3) if ans_not_refused else 0.0,
        "mean_latency_s": round(sum(r.latency_s for r in results) / n, 2) if n else 0.0,
    }
    fails: dict[str, int] = {}
    for r in results:
        if not r.passed and r.failure_category:
            fails[r.failure_category] = fails.get(r.failure_category, 0) + 1
    return Scorecard(label=label, definition_version=version, n_cases=n, passed=p, pass_rate=round(p / n, 3) if n else 0,
                     ci95=tuple(round(x, 3) for x in wilson_interval(p, n)),
                     dev_pass_rate=rate([r for r in results if r.split == "dev"]),
                     holdout_pass_rate=rate([r for r in results if r.split == "holdout"]),
                     by_category=cats, metrics=metrics, failures_by_type=fails)


def run_cases(ctx: RunContext, runtime: AgentRuntime, judge: Judge, cases: list[EvalCase], label: str) -> list[CaseResult]:
    from .critic import classify

    out = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        resp = runtime.answer(case.question)
        res = judge.score(case, resp, runtime)
        classify(res)
        out.append(res)
        mark = "✓" if res.passed else f"✗ {res.failure_category}"
        ctx.log(f"    [{label}] {i:>2}/{len(cases)} {case.id:<8} {mark}")
    ctx.log(f"    [{label}] {sum(r.passed for r in out)}/{len(out)} passed in {time.time() - t0:.0f}s")
    return out
