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


def _topic_in_excerpts(topic: str, hits) -> str | None:
    """Id of a top-3 excerpt that contains every word of the topic name (the document's own name counts:
    'leave policy' is covered by leave_policy.pdf). None when no excerpt does."""
    for c, _ in hits[:3]:
        text = c.text + " " + c.doc_id.rsplit(".", 1)[0].replace("_", " ")
        if coverage(topic, text) >= 0.99:
            return c.chunk_id
    return None


class _Verdict(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    evidence_chunk_ids: list[str] = []
    missing: str = ""


def brief_requested(topic: str, brief: str) -> bool:
    """True if most of the topic's words appear in the brief (the requester asked for it)."""
    from ..textutil import tokens

    tt = set(tokens(topic))
    return bool(tt) and len(tt & set(tokens(brief))) / len(tt) >= 0.6


def assess(ctx: RunContext, req: Requirements, docs, brief: str = "") -> GroundabilityReport:
    retr = Retriever(docs, RetrievalConfig(chunk_size=160, chunk_overlap=30, top_k=6), llm=None)
    results: list[TopicGrounding] = []
    from ..docs.loader import table_computable, table_match

    # Topics the BRIEF asked for but intake already put on the refuse list (e.g. "salary bands") are checked
    # too, so the gap is reported - but they never count towards the groundable fraction.
    requested_refusals = [RefuseTopic(topic=t.topic, reason=t.reason) for t in req.must_refuse_topics
                          if brief and brief_requested(t.topic, brief)]
    extra_names = {t.topic for t in requested_refusals}
    from ..schemas import Topic as _Topic
    to_check = list(req.must_answer_topics) + [_Topic(topic=t.topic, description=t.reason) for t in requested_refusals]

    for t in to_check:
        query = f"{t.topic} {t.description}"
        ctable, ctool = table_computable(t.topic, docs)
        if ctable:  # e.g. "order totals" = price column x quantity; "arrival date" = today + lead time column
            results.append(TopicGrounding(topic=t.topic, verdict="supported", evidence_chunk_ids=[f"{ctable}:columns"],
                                          note=f"computed from {ctable} columns with the {ctool} tool",
                                          lexical_overlap=1.0))
            ctx.log(f"  ✓ {t.topic}: supported - computed from {ctable} with {ctool}")
            continue
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
            # small models often forget to cite. Only keep the claim if the top excerpt contains every
            # word of the topic name - and then only as 'partial', never 'supported'.
            found = _topic_in_excerpts(t.topic, hits)
            if found:
                verdict, adjusted, ids = "partial", True, [found]
                note = (f"guard: model said '{v.verdict}' without citing; excerpt {found} contains the "
                        f"topic, so kept as partial. {note}").strip()
            else:
                verdict, adjusted = "unsupported", True
                note = f"guard: model said '{v.verdict}' but cited no valid excerpt. {note}".strip()
        elif verdict == "supported" and overlap < MIN_EVIDENCE_OVERLAP:
            verdict, adjusted = "partial", True
            note = f"guard: cited excerpts barely mention the topic (overlap {overlap:.2f}). {note}".strip()
        elif verdict == "unsupported" and _topic_in_excerpts(t.topic, hits):
            # every word of the topic name appears in a top excerpt: a false gap is likelier than a real one
            found = _topic_in_excerpts(t.topic, hits)
            verdict, adjusted, ids = "partial", True, [found]
            note = (f"guard: model said unsupported, but excerpt {found} contains every word of the "
                    f"topic - changed to partial. {note}").strip()
        results.append(TopicGrounding(topic=t.topic, verdict=verdict, evidence_chunk_ids=ids, note=note,
                                      lexical_overlap=round(overlap, 2), adjusted_by_guard=adjusted))
        mark = {"supported": "✓", "partial": "~", "unsupported": "✗"}[verdict]
        ctx.log(f"  {mark} {t.topic}: {verdict}{' (guard-adjusted)' if adjusted else ''}")

    for r in results:
        if r.topic in extra_names:
            r.note = ("requested in the brief; intake already set it to REFUSE. " + r.note).strip()
    core = [r for r in results if r.topic not in extra_names]
    n = len(core) or 1
    frac = (sum(r.verdict == "supported" for r in core) + 0.5 * sum(r.verdict == "partial" for r in core)) / n
    gaps = [r.topic for r in results if r.verdict == "unsupported"]
    blocking = frac < BLOCK_BELOW
    summary = (f"{sum(r.verdict == 'supported' for r in core)} supported, "
               f"{sum(r.verdict == 'partial' for r in core)} partial, "
               f"{sum(r.verdict == 'unsupported' for r in core)} unsupported "
               f"(groundable fraction {frac:.0%}).")
    if gaps:
        summary += " Unsupported topics will be REFUSED by the agent instead of answered: " + "; ".join(gaps) + "."
    if blocking:
        summary += " BLOCKING: most of the brief cannot be answered from these documents."
    return GroundabilityReport(topics=results, flagged_gaps=gaps, groundable_fraction=round(frac, 3),
                               blocking=blocking, summary=summary)


def apply_to_requirements(req: Requirements, rep: GroundabilityReport) -> Requirements:
    from ..textutil import tokens

    req = req.model_copy(deep=True)
    # Safety: a request restored from the brief that overlaps topics the documents DO support is too broad
    # to refuse (refusing "answers HR policy questions ... leave" would break the agent). Keep it, as partial.
    ok_tokens = set()
    for r in rep.topics:
        if r.verdict != "unsupported":
            ok_tokens |= set(tokens(r.topic))
    restored = {t.topic for t in req.must_answer_topics if "restored by coverage check" in t.description}
    for r in rep.topics:
        rt = set(tokens(r.topic))
        if r.topic in restored and r.verdict == "unsupported" and rt and len(rt & ok_tokens) / len(rt) >= 0.5:
            r.verdict, r.adjusted_by_guard = "partial", True
            r.note = ("guard: broad request restored from the brief overlaps supported topics - kept as partial "
                      "instead of being refused. " + r.note).strip()
            if r.topic in rep.flagged_gaps:
                rep.flagged_gaps.remove(r.topic)
    gap_set = set(rep.flagged_gaps)
    already = {t.topic for t in req.must_refuse_topics}
    removed = [t for t in req.must_answer_topics if t.topic in gap_set and t.topic not in already]
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


def run_groundability(ctx: RunContext, req: Requirements, docs, brief: str = ""
                      ) -> tuple[Requirements, GroundabilityReport]:
    ctx.stage("2. Groundability guard")
    rep = assess(ctx, req, docs, brief)
    ctx.save_json("02_requirements/groundability.json", rep)
    ctx.save_text("02_requirements/groundability.md", report_markdown(rep))
    final = apply_to_requirements(req, rep)
    ctx.log(f"  {rep.summary}", "yellow" if rep.flagged_gaps else "green")
    return final, rep
