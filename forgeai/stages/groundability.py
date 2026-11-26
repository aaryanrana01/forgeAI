"""Requirement 2 - Groundability guard.

For every must-answer topic: retrieve evidence, ask the model whether the
documents really support it, then *check the model's verdict* with
deterministic rules (cited ids must exist, cited text must overlap the topic).
Unsupported topics are flagged and turned into explicit refusal topics, so the
generated agent cannot hallucinate the gap away. If most of the brief is not
groundable, the factory stops."""

from __future__ import annotations

from typing import Literal

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..llm import LLMError
from ..retrieval.index import Retriever, coverage
from ..schemas import GroundabilityReport, RefuseTopic, Requirements, RetrievalConfig, TopicGrounding

BLOCK_BELOW = 0.5          # stop the factory if less than half the brief is groundable
MIN_EVIDENCE_OVERLAP = 0.25


class _Verdict(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    evidence_chunk_ids: list[str] = []
    missing: str = ""


def assess(ctx: RunContext, req: Requirements, docs) -> GroundabilityReport:
    retr = Retriever(docs, RetrievalConfig(chunk_size=160, chunk_overlap=30, top_k=6), llm=None)
    results: list[TopicGrounding] = []
    from ..docs.loader import table_match

    for t in req.must_answer_topics:
        query = f"{t.topic} {t.description}"
        table, cols = table_match(query, docs)
        if table:  # structured data: support is decided by the table's columns, not by sampled rows
            results.append(TopicGrounding(topic=t.topic, verdict="supported", evidence_chunk_ids=[f"{table}:columns"],
                                          note=f"answerable from table {table} (columns matching: {', '.join(cols)})",
                                          lexical_overlap=1.0))
            ctx.log(f"  ✓ {t.topic}: supported by table {table} ({', '.join(cols)})")
            continue
        hits = retr.search(query, top_k=6)
        excerpts = "\n\n".join(f"[{c.chunk_id}] {c.text[:900]}" for c, _ in hits) or "(nothing retrieved)"
        valid = {c.chunk_id: c for c, _ in hits}
        try:
            v = ctx.llm.json(prompts.split("groundability", topic=t.topic, description=t.description,
                                           excerpts=excerpts), _Verdict, task="groundability", max_tokens=300)
        except LLMError:
            v = _Verdict(verdict="partial", missing="judge failed; treated as partial")
        ids = [i for i in v.evidence_chunk_ids if i in valid]
        overlap = max((coverage(query, valid[i].text) for i in ids), default=0.0)
        verdict, adjusted, note = v.verdict, False, v.missing
        # --- deterministic guard over the model's verdict -----------------
        if verdict in ("supported", "partial") and not ids:
            verdict, adjusted = "unsupported", True
            note = f"guard: model said '{v.verdict}' but cited no valid excerpt. {note}".strip()
        elif verdict == "supported" and overlap < MIN_EVIDENCE_OVERLAP:
            verdict, adjusted = "partial", True
            note = f"guard: cited excerpts barely mention the topic (overlap {overlap:.2f}). {note}".strip()
        elif verdict == "unsupported" and hits and coverage(t.topic, hits[0][0].text) >= 0.99:
            # every word of the topic name appears in the top excerpt: a false gap is likelier than a real one
            verdict, adjusted = "partial", True
            ids = [hits[0][0].chunk_id]
            note = (f"guard: model said unsupported, but excerpt {hits[0][0].chunk_id} contains every word of the "
                    f"topic - downgraded to partial. {note}").strip()
        results.append(TopicGrounding(topic=t.topic, verdict=verdict, evidence_chunk_ids=ids, note=note,
                                      lexical_overlap=round(overlap, 2), adjusted_by_guard=adjusted))
        mark = {"supported": "✓", "partial": "~", "unsupported": "✗"}[verdict]
        ctx.log(f"  {mark} {t.topic}: {verdict}{' (guard-adjusted)' if adjusted else ''}")

    n = len(results) or 1
    frac = (sum(r.verdict == "supported" for r in results) + 0.5 * sum(r.verdict == "partial" for r in results)) / n
    gaps = [r.topic for r in results if r.verdict == "unsupported"]
    blocking = frac < BLOCK_BELOW
    summary = (f"{sum(r.verdict == 'supported' for r in results)} supported, "
               f"{sum(r.verdict == 'partial' for r in results)} partial, {len(gaps)} unsupported "
               f"(groundable fraction {frac:.0%}).")
    if gaps:
        summary += " Unsupported topics will be REFUSED by the agent instead of answered: " + "; ".join(gaps) + "."
    if blocking:
        summary += " BLOCKING: most of the brief cannot be answered from these documents."
    return GroundabilityReport(topics=results, flagged_gaps=gaps, groundable_fraction=round(frac, 3),
                               blocking=blocking, summary=summary)


def apply_to_requirements(req: Requirements, rep: GroundabilityReport) -> Requirements:
    req = req.model_copy(deep=True)
    gap_set = set(rep.flagged_gaps)
    removed = [t for t in req.must_answer_topics if t.topic in gap_set]
    req.must_answer_topics = [t for t in req.must_answer_topics if t.topic not in gap_set]
    for t in removed:
        req.must_refuse_topics.append(RefuseTopic(
            topic=t.topic, reason="Requested in the brief but NOT covered by the documents "
                                  "(flagged by groundability guard) - refuse and redirect."))
    for r in rep.topics:
        if r.verdict == "partial":
            req.constraints.append(f"Topic '{r.topic}' is only partly documented; answer only what the "
                                   f"documents state and refuse the rest. Missing: {r.note or 'unspecified'}")
    return req


def report_markdown(rep: GroundabilityReport) -> str:
    md = ["# Groundability report", "", rep.summary, "", "| Topic | Verdict | Evidence | Note |", "|---|---|---|---|"]
    for r in rep.topics:
        md.append(f"| {r.topic} | {r.verdict}{' (guard)' if r.adjusted_by_guard else ''} | "
                  f"{', '.join(r.evidence_chunk_ids) or '-'} | {r.note.replace('|', '/')} |")
    if rep.flagged_gaps:
        md += ["", "## Flagged gaps", "The brief asks for these but the documents cannot support them. "
               "The agent is configured to refuse them rather than guess:"]
        md += [f"- {g}" for g in rep.flagged_gaps]
    return "\n".join(md) + "\n"


def run_groundability(ctx: RunContext, req: Requirements, docs) -> tuple[Requirements, GroundabilityReport]:
    ctx.stage("2. Groundability guard")
    rep = assess(ctx, req, docs)
    ctx.save_json("02_requirements/groundability.json", rep)
    ctx.save_text("02_requirements/groundability.md", report_markdown(rep))
    final = apply_to_requirements(req, rep)
    ctx.log(f"  {rep.summary}", "yellow" if rep.flagged_gaps else "green")
    return final, rep
