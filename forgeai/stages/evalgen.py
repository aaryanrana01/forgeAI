"""Requirement 4 - Eval generator.

Builds the test set FROM THE DOCUMENTS (never hand-written). The model
proposes cases; deterministic checks then verify them, and every rejected
case is logged with the reason:

  answerable      one passage -> question + key facts; each key fact must be
                  found verbatim(ish) in the passage, else it is dropped
  cross_doc       two related passages from different documents; needs a
                  verified fact from each
  out_of_scope    must-refuse topics, groundability gaps, near-domain and
                  off-domain questions; dropped if the documents actually
                  answer them (checked by retrieval + model)
  edge_ambiguous  messy paraphrases of answerable cases (same facts)
  edge_injection  attempts to talk the agent into a must-refuse topic
  tool            CSV-backed lookups/totals/dates whose expected values are
                  COMPUTED BY CODE from the table, not by the model
"""

from __future__ import annotations

import random
import re
from typing import Literal

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..llm import LLMError
from ..retrieval.index import Retriever
from ..schemas import EvalCase, EvalSet, GroundabilityReport, Requirements, RetrievalConfig
from ..textutil import fact_present, jaccard, normalize, numbers, numbers_with_words, tokens

PROMPTS_USED = ["evalgen_answerable", "evalgen_crossdoc", "evalgen_out_of_scope", "evalgen_refusal_check",
                "evalgen_paraphrase", "evalgen_injection", "evalgen_table"]

DEFAULT_PLAN = {"answerable": 10, "cross_doc": 3, "out_of_scope": 5, "edge_ambiguous": 3,
                "edge_injection": 2, "tool": 4}
MIN_CASES = 20


class _QA(BaseModel):
    question: str
    answer: str = ""
    key_facts: list[str]
    evidence_quote: str = ""


class _Cross(BaseModel):
    question: str
    answer: str = ""
    facts_from_a: list[str]
    facts_from_b: list[str]


class _OOSItem(BaseModel):
    question: str
    kind: Literal["must_refuse", "gap", "near_domain", "off_domain"] = "near_domain"
    target: str = ""


class _OOS(BaseModel):
    questions: list[_OOSItem]


class _Check(BaseModel):
    answerable: bool
    evidence_id: str = ""


class _Q(BaseModel):
    question: str


# section numbering like "3. " or "4.2 " at the start of a fact/heading - but NOT "12 days"
_NUMBERING = re.compile(r"^\s*(?:\d+[.)]|\d+(?:\.\d+)+)\s+")

PARAPHRASE_STYLES = [
    "very casual and short, like a quick chat message, with one small typo",
    "vague, using 'it' or 'that thing' and leaving out the formal policy name",
    "long-winded with an irrelevant personal detail before the actual question",
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.split()) >= 4]


def _best_sentence(passage: str, hint: str) -> str:
    sents = _sentences(passage) or [passage]
    return max(sents, key=lambda s: jaccard(s, hint))


class EvalGenerator:
    def __init__(self, ctx: RunContext, req: Requirements, gr: GroundabilityReport, docs, plan: dict | None = None):
        self.ctx, self.req, self.gr, self.docs = ctx, req, gr, docs
        self.plan = {**DEFAULT_PLAN, **(plan or {})}
        self.rng = random.Random(ctx.settings.seed)
        # The eval set must not depend on the agent's chunking, so it uses its own fixed index.
        self.index = Retriever(docs, RetrievalConfig(chunk_size=110, chunk_overlap=0, prepend_headings=False, top_k=6))
        self.cases: list[EvalCase] = []
        self.dropped: list[dict] = []
        self.parent: dict[str, str] = {}
        self.headings = {normalize(_NUMBERING.sub("", h)).strip(" .")
                         for d in docs for h in d.headings}
        self._n = 0

    # --------------------------------------------------------------- helpers
    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}-{self._n:02d}"

    def _drop(self, kind: str, reason: str, payload: dict | str) -> None:
        self.dropped.append({"kind": kind, "reason": reason, "payload": payload})

    def _is_dup(self, q: str) -> bool:
        return any(jaccard(q, c.question) > 0.6 for c in self.cases)

    def _verify_facts(self, facts: list[str], passage: str, question: str = "") -> list[str]:
        """Keep only facts that (1) are really in the passage, (2) are not already given away by the
        question, (3) are not just a section heading, and (4) carry information: a number, or at least
        two content words. Seen in real runs: 'Purpose', 'Scope', '3. Air Travel ...', 'Tier-1 cities'."""
        ok = []
        for f in facts:
            f = _NUMBERING.sub("", f.strip().strip('"').strip())
            n_words = len(f.split())
            if not 1 <= n_words <= 12:
                continue
            if not fact_present(f, passage, token_threshold=0.85):
                continue
            if question and fact_present(f, question, token_threshold=0.85):
                continue
            if normalize(f).strip(" .") in self.headings:
                continue
            if not numbers_with_words(f) and len(tokens(f)) < 2:
                continue
            ok.append(f)
        return ok

    def _seed_chunks(self) -> list:
        """Information-dense passages, spread across documents."""
        by_doc: dict[str, list] = {}
        for c in self.index.chunks:
            d = next(x for x in self.docs if x.doc_id == c.doc_id)
            if d.kind == "csv" or len(c.text.split()) < 35:
                continue
            density = len(numbers(c.text)) * 2 + len(set(tokens(c.text))) / 20
            by_doc.setdefault(c.doc_id, []).append((density, c))
        for k in by_doc:
            ranked = sorted(by_doc[k], key=lambda x: -x[0])
            top = ranked[: max(4, len(ranked) * 2 // 3)]
            self.rng.shuffle(top)
            by_doc[k] = [c for _, c in top] + [c for _, c in ranked[len(top):]]
        order, docs_cycle = [], list(by_doc)
        while any(by_doc.values()):
            for k in docs_cycle:
                if by_doc[k]:
                    order.append(by_doc[k].pop(0))
        return order

    @property
    def _scope(self) -> str:
        return f"{self.req.agent_name}: {self.req.scope}"

    # ------------------------------------------------------------ answerable
    def gen_answerable(self, n: int, seeds: list) -> None:
        made = 0
        while seeds and made < n:
            c = seeds.pop(0)
            avoid = "; ".join(x.question for x in self.cases[-8:]) or "(none)"
            try:
                qa = self.ctx.llm.json(prompts.split("evalgen_answerable", doc_id=c.doc_id, passage=c.text,
                                                     scope=self._scope, audience=self.req.audience, avoid=avoid),
                                       _QA, task="evalgen_answerable", max_tokens=500, temperature=0.3)
            except LLMError as e:
                self._drop("answerable", f"generation failed: {e}", c.chunk_id)
                continue
            facts = self._verify_facts(qa.key_facts, c.text, qa.question)
            if not facts:
                self._drop("answerable", "no key fact could be verified in the source passage",
                           {"chunk": c.chunk_id, "question": qa.question, "claimed_facts": qa.key_facts})
                continue
            if all(fact_present(f, qa.question) for f in facts):
                self._drop("answerable", "question gives away its own answer", qa.question)
                continue
            if self._is_dup(qa.question):
                self._drop("answerable", "near-duplicate question", qa.question)
                continue
            ev = qa.evidence_quote if normalize(qa.evidence_quote) and normalize(qa.evidence_quote) in normalize(c.text) \
                else _best_sentence(c.text, " ".join(facts))
            self.cases.append(EvalCase(
                id=self._id("ans"), category="answerable", question=qa.question.strip(), should_refuse=False,
                expected_sources=[c.doc_id], key_facts=facts, evidence=[ev], reference_answer=qa.answer,
                generation={"prompt": "evalgen_answerable", "seed_chunk": c.chunk_id, "source_passage": c.text}))
            made += 1

    # -------------------------------------------------------------- cross doc
    def gen_cross(self, n: int) -> None:
        text_docs = [d.doc_id for d in self.docs if d.kind != "csv"]
        if len(text_docs) < 2:
            self._drop("cross_doc", "fewer than two text documents - no cross-document cases possible", "")
            return
        pairs = []
        chunks = [c for c in self.index.chunks if c.doc_id in text_docs and len(c.text.split()) > 30]
        for a in chunks:
            scores = self.index.bm25.scores(a.text)
            for j, s in enumerate(scores):
                b = self.index.chunks[j]
                if b.doc_id != a.doc_id and b.doc_id in text_docs and len(b.text.split()) > 30:
                    pairs.append((s, a, b))
        pairs.sort(key=lambda x: -x[0])
        used, made = set(), 0
        for s, a, b in pairs:
            if made >= n or s <= 0:
                break
            key = tuple(sorted((a.chunk_id, b.chunk_id)))
            if key in used or a.chunk_id in {u for k in used for u in k}:
                continue
            used.add(key)
            try:
                r = self.ctx.llm.json(prompts.split("evalgen_crossdoc", doc_a=a.doc_id, passage_a=a.text,
                                                    doc_b=b.doc_id, passage_b=b.text, scope=self._scope),
                                      _Cross, task="evalgen_crossdoc", max_tokens=600, temperature=0.3)
            except LLMError as e:
                self._drop("cross_doc", f"generation failed: {e}", key)
                continue
            fa = self._verify_facts(r.facts_from_a, a.text, r.question)
            fb = self._verify_facts(r.facts_from_b, b.text, r.question)
            if not fa or not fb:
                self._drop("cross_doc", "could not verify a fact from each document",
                           {"question": r.question, "a": r.facts_from_a, "b": r.facts_from_b})
                continue
            if self._is_dup(r.question):
                self._drop("cross_doc", "near-duplicate question", r.question)
                continue
            self.cases.append(EvalCase(
                id=self._id("x"), category="cross_doc", question=r.question.strip(), should_refuse=False,
                expected_sources=[a.doc_id, b.doc_id], key_facts=fa + fb,
                evidence=[_best_sentence(a.text, " ".join(fa)), _best_sentence(b.text, " ".join(fb))],
                reference_answer=r.answer, generation={"prompt": "evalgen_crossdoc", "chunks": list(key)}))
            made += 1

    # ----------------------------------------------------------- out of scope
    def _answerable_by_docs(self, question: str) -> tuple[bool, str]:
        hits = self.index.search(question, top_k=4)
        if not hits:
            return False, ""
        passages = "\n\n".join(f"[{c.chunk_id}] {c.text}" for c, _ in hits)
        try:
            chk = self.ctx.llm.json(prompts.split("evalgen_refusal_check", question=question, passages=passages),
                                    _Check, task="evalgen_refusal_check", max_tokens=120)
        except LLMError:
            return False, ""
        valid = {c.chunk_id for c, _ in hits}
        return (chk.answerable and chk.evidence_id in valid), chk.evidence_id

    def gen_out_of_scope(self, n: int) -> None:
        covered = ", ".join(t.topic for t in self.req.must_answer_topics)
        refuse = "; ".join(t.topic for t in self.req.must_refuse_topics) or "(none listed)"
        gaps = "; ".join(self.gr.flagged_gaps) or "(none)"
        try:
            r = self.ctx.llm.json(prompts.split("evalgen_out_of_scope", scope=self._scope, refuse=refuse, gaps=gaps,
                                                covered=covered, n=n + 3), _OOS, task="evalgen_out_of_scope",
                                  max_tokens=900, temperature=0.4)
        except LLMError as e:
            self._drop("out_of_scope", f"generation failed: {e}", "")
            return
        # prefer variety of kinds: gaps first (most tempting to hallucinate), then others round-robin
        items = sorted(r.questions, key=lambda q: ["gap", "must_refuse", "near_domain", "off_domain"].index(q.kind))
        made = 0
        for q in items:
            if made >= n:
                break
            if self._is_dup(q.question):
                self._drop("out_of_scope", "near-duplicate question", q.question)
                continue
            ans, ev = self._answerable_by_docs(q.question)
            if ans:
                self._drop("out_of_scope", f"documents actually answer it (evidence {ev}) - not a valid refusal test",
                           q.question)
                continue
            self.cases.append(EvalCase(id=self._id("oos"), category="out_of_scope", question=q.question.strip(),
                                       should_refuse=True, generation={"prompt": "evalgen_out_of_scope",
                                                                       "kind": q.kind, "target": q.target}))
            made += 1

    # ------------------------------------------------------------------ edges
    def gen_paraphrases(self, n: int) -> None:
        bases = [c for c in self.cases if c.category == "answerable"]
        self.rng.shuffle(bases)
        made = 0
        for i, base in enumerate(bases):
            if made >= n:
                break
            style = PARAPHRASE_STYLES[made % len(PARAPHRASE_STYLES)]
            try:
                p = self.ctx.llm.json(prompts.split("evalgen_paraphrase", question=base.question, style=style),
                                      _Q, task="evalgen_paraphrase", max_tokens=150, temperature=0.5)
            except LLMError:
                continue
            q = p.question.strip()
            if not q or jaccard(q, base.question) > 0.85 or all(fact_present(f, q) for f in base.key_facts):
                self._drop("edge_ambiguous", "paraphrase too close to original or leaks answer", q)
                continue
            cid = self._id("amb")
            self.parent[cid] = base.id
            self.cases.append(base.model_copy(update={
                "id": cid, "category": "edge_ambiguous", "question": q,
                "generation": {"prompt": "evalgen_paraphrase", "style": style, "parent": base.id}}))
            made += 1

    def gen_injections(self, n: int) -> None:
        targets = [t.topic for t in self.req.must_refuse_topics] or ["confidential information"]
        for i in range(n):
            t = targets[i % len(targets)]
            try:
                p = self.ctx.llm.json(prompts.split("evalgen_injection", scope=self._scope, target=t), _Q,
                                      task="evalgen_injection", max_tokens=150, temperature=0.5)
            except LLMError:
                continue
            if p.question.strip() and not self._is_dup(p.question):
                self.cases.append(EvalCase(id=self._id("inj"), category="edge_injection", question=p.question.strip(),
                                           should_refuse=True, generation={"prompt": "evalgen_injection", "target": t}))

    # ------------------------------------------------------------------ table
    @staticmethod
    def _roles(cols: list[str], rows: list[dict]) -> dict:
        def num(col):
            vals = [r.get(col, "") for r in rows]
            ok = sum(1 for v in vals if re.fullmatch(r"-?[\d,]+(\.\d+)?", v.strip() or "x"))
            return ok >= 0.9 * len(vals)
        low = {c: c.lower() for c in cols}
        pick = lambda keys, numeric=None: next((c for c in cols if any(k in low[c] for k in keys)
                                                and (numeric is None or num(c) == numeric)), None)
        idc = pick(["part_no", "part no", "part_number", "sku", "item_code", "code", "id"]) or cols[0]
        return {"id": idc,
                "name": pick(["description", "name", "item", "title"], numeric=False),
                "price": pick(["price", "cost", "rate"], numeric=True),
                "stock": pick(["stock", "qty", "quantity", "on_hand", "available"], numeric=True),
                "lead": pick(["lead"], numeric=True)}

    def gen_table(self, n: int) -> None:
        csvs = [d for d in self.docs if d.kind == "csv" and d.rows]
        if not csvs:
            return
        d = csvs[0]
        roles = self._roles(d.columns, d.rows)
        rows = d.rows[:]
        self.rng.shuffle(rows)
        specs = []
        for i, row in enumerate(rows):
            item = row[roles["id"]]
            name = row.get(roles["name"], "") if roles["name"] else ""
            kind = ["total", "lookup", "date", "stock"][i % 4]
            if kind == "total" and roles["price"]:
                qty = self.rng.choice([2, 3, 4, 5, 6, 8, 10, 12])
                price = float(row[roles["price"]].replace(",", ""))
                total = round(qty * price, 2)
                specs.append(("total", row, item, name,
                              f"Ask for the total cost of buying {qty} units of this item.",
                              [f"{total:,.2f}"], ["csv_lookup", "calculator"]))
            elif kind == "lookup" and roles["price"]:
                specs.append(("lookup", row, item, name, f"Ask for the unit price ({roles['price']}) of this item.",
                              [row[roles["price"]]], ["csv_lookup"]))
            elif kind == "date" and roles["lead"]:
                days = int(float(row[roles["lead"]]))
                specs.append(("date", row, item, name,
                              "Ask by which date the item would arrive if ordered today (lead time is in the table).",
                              [f"date:+{days}"], ["csv_lookup", "current_date"]))
            elif kind == "stock" and roles["stock"]:
                specs.append(("stock", row, item, name, "Ask how many units of this item are in stock.",
                              [row[roles["stock"]]], ["csv_lookup"]))
            if len(specs) >= n:
                break
        for kind, row, item, name, task, facts, tools in specs:
            try:
                p = self.ctx.llm.json(prompts.split("evalgen_table", scope=self._scope, row=row, task=task,
                                                    item_id=item), _Q, task="evalgen_table", max_tokens=150,
                                      temperature=0.3)
                q = p.question.strip()
            except LLMError:
                q = ""
            if not q or (item.lower() not in q.lower() and not (name and jaccard(name, q) > 0.2)):
                qty = re.search(r"buying (\d+)", task)
                q = {"total": f"What is the total cost for {qty.group(1) if qty else 2} units of part {item}?",
                     "lookup": f"What is the unit price of part {item}?",
                     "date": f"If I order part {item} today, when should it arrive?",
                     "stock": f"How many units of part {item} do we have in stock?"}[kind]
                self._drop("tool", "model question did not mention the item; used template question", {"item": item})
            if any(fact_present(f, q) for f in facts if not f.startswith("date:") and f != item):
                self._drop("tool", "question leaks the expected value", q)
                continue
            self.cases.append(EvalCase(
                id=self._id("tool"), category="tool", question=q, should_refuse=False, expected_sources=[d.doc_id],
                key_facts=facts, evidence=[" | ".join(f"{k}: {v}" for k, v in row.items())],
                expected_tools=tools, generation={"prompt": "evalgen_table", "kind": kind, "item": item, "computed_by": "code"}))

    # ------------------------------------------------------------------ split
    def assign_splits(self, holdout_frac: float = 0.3) -> None:
        by_cat: dict[str, list[EvalCase]] = {}
        for c in self.cases:
            if c.id not in self.parent:
                by_cat.setdefault(c.category, []).append(c)
        for cat, items in by_cat.items():
            self.rng.shuffle(items)
            k = round(len(items) * holdout_frac) if len(items) >= 3 else 0
            for i, c in enumerate(items):
                c.split = "holdout" if i < k else "dev"
        ids = {c.id: c for c in self.cases}
        for child, par in self.parent.items():  # paraphrases stay with their parent: no dev->holdout leakage
            ids[child].split = ids[par].split

    # -------------------------------------------------------------------- run
    def run(self) -> EvalSet:
        seeds = self._seed_chunks()
        self.ctx.log(f"  {len(seeds)} candidate passages across {len({c.doc_id for c in seeds})} documents")
        self.gen_answerable(self.plan["answerable"], seeds)
        self.gen_cross(self.plan["cross_doc"])
        self.gen_out_of_scope(self.plan["out_of_scope"])
        self.gen_table(self.plan["tool"])
        self.gen_paraphrases(self.plan["edge_ambiguous"])
        self.gen_injections(self.plan["edge_injection"])
        rounds = 0
        while len(self.cases) < MIN_CASES and rounds < 3:   # top up after verification losses
            if not seeds:  # every passage used once: go round again for a second, different question
                seeds = self._seed_chunks()
            self.gen_answerable(MIN_CASES - len(self.cases), seeds)
            rounds += 1
        self.assign_splits()
        counts: dict[str, int] = {}
        for c in self.cases:
            counts[c.category] = counts.get(c.category, 0) + 1
        meta = {"n_cases": len(self.cases), "by_category": counts,
                "by_split": {s: sum(c.split == s for c in self.cases) for s in ("dev", "holdout")},
                "generator_model": self.ctx.settings.model, "seed": self.ctx.settings.seed,
                "prompts": prompts.fingerprint(*PROMPTS_USED), "n_dropped": len(self.dropped),
                "note": "Generated automatically from the documents; every key fact was verified against its "
                        "source passage by code. Dropped candidates are listed in dropped_cases.json."}
        return EvalSet(cases=self.cases, meta=meta)


def evalset_markdown(es: EvalSet) -> str:
    md = ["# Generated eval set", "", f"{es.meta.get('n_cases')} cases - {es.meta.get('by_category')} - "
          f"splits {es.meta.get('by_split')}", "", "| id | split | category | question | expected |", "|---|---|---|---|---|"]
    for c in es.cases:
        exp = "REFUSE" if c.should_refuse else ("; ".join(c.key_facts) + f" [{', '.join(c.expected_sources)}]")
        md.append(f"| {c.id} | {c.split} | {c.category} | {c.question.replace('|', '/')} | {exp.replace('|', '/')} |")
    return "\n".join(md) + "\n"


def run_evalgen(ctx: RunContext, req: Requirements, gr: GroundabilityReport, docs, plan: dict | None = None) -> EvalSet:
    ctx.stage("4. Eval generator")
    gen = EvalGenerator(ctx, req, gr, docs, plan)
    es = gen.run()
    ctx.save_json("04_evals/eval_set.json", es)
    ctx.save_text("04_evals/eval_set.md", evalset_markdown(es))
    ctx.save_json("04_evals/dropped_cases.json", gen.dropped)
    ctx.log(f"  {len(es.cases)} cases kept {es.meta['by_category']}; {len(gen.dropped)} candidates rejected by checks")
    if len(es.cases) < MIN_CASES:
        ctx.log(f"  ! only {len(es.cases)} cases survived verification (target {MIN_CASES}) - reported honestly", "yellow")
    return es
