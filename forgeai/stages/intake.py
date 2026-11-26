"""Requirement 1 - Intake interviewer.

brief + document inventory -> <=5 clarifying questions -> answers (live CLI,
the requester's written notes, or explicit default assumptions) -> structured
requirements document (JSON + Markdown)."""

from __future__ import annotations

import re

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..docs.loader import inventory_text
from ..llm import LLMError
from ..schemas import QAPair, QuestionList, Requirements, Topic

MAX_QUESTIONS = 5


class _NoteLine(BaseModel):
    line: int


class _Requests(BaseModel):
    requests: list[str]


def _brief_clauses(brief: str) -> list[str]:
    """Deterministic fallback: split the brief into request-like clauses."""
    parts = re.split(r"[.;:]\s+|,\s+|\s+-\s+|\s+and\s+(?=[a-z]+\s)", brief)
    return [p.strip(" .") for p in parts if len(p.split()) >= 4]


_FRAMING = re.compile(r"^(?:i|we)\s+(?:need|want)\s+|^(?:please\s+)?(?:build|create|make)\s+|"
                      r"^(?:it\s+)?would\s+(?:also\s+)?be\s+great\s+if\s+it\s+could\s+|^it\s+should\s+(?:also\s+)?"
                      r"(?:be\s+able\s+to\s+)?|^also\s+", re.I)


def _clean_request(r: str) -> str:
    """Strip framing ('I need ...', 'it would also be great if it could ...'); drop the sentence that just
    describes the whole assistant, and anything too long to be one request."""
    r = r.strip(" .-")
    for _ in range(2):
        r = _FRAMING.sub("", r).strip()
    if re.search(r"\bassistant\b", r, re.I) or not 2 <= len(r.split()) <= 14:
        return ""
    return r


def ensure_brief_coverage(ctx: RunContext, brief: str, req: Requirements) -> tuple[Requirements, list[str]]:
    """Every request in the brief must survive into the requirements (as a topic to answer or to refuse).
    Small models silently drop requests - e.g. 'track the live shipment status' became 'order status' and
    the gap was never flagged. Missing requests are added back verbatim as must-answer topics, so the
    groundability guard judges them (and flags them if the documents cannot support them)."""
    from ..textutil import tokens

    requests: list[str] = []
    try:
        res = ctx.llm.json(prompts.split("intake_brief_requests", brief=brief), _Requests,
                           task="intake_brief_requests", max_tokens=400)
        bt = set(tokens(brief))
        for r in res.requests:  # keep only phrases really taken from the brief
            rt = set(tokens(r))
            if len(rt) >= 2 and len(rt & bt) / len(rt) >= 0.7:
                requests.append(r.strip())
    except LLMError:
        pass
    if not requests:
        requests = _brief_clauses(brief)
    requests = [c for c in (_clean_request(r) for r in requests) if c]
    covered = set()
    for t in req.must_answer_topics:
        covered |= set(tokens(f"{t.topic} {t.description}"))
    for t in req.must_refuse_topics:
        covered |= set(tokens(f"{t.topic} {t.reason}"))
    added = []
    for r in requests:
        rt = set(tokens(r))
        if rt and len(rt & covered) / len(rt) < 0.6:
            req.must_answer_topics.append(Topic(topic=r, description="requested in the brief (restored by coverage check)"))
            covered |= rt
            added.append(r)
    return req, added


# words that appear in almost every intake question, so they cannot identify the matching note line
_GENERIC_Q = {"assistant", "user", "staff", "shore", "respons", "response", "question", "expect", "specific", "provid",
              "any", "there", "should", "would", "will", "help", "need", "employee", "interact", "regard",
              "handle", "ensure", "follow", "aware", "appropriately", "primary", "exactly"}


def note_lines(notes: str) -> list[str]:
    return [ln.strip().lstrip("-").strip() for ln in notes.splitlines() if ln.strip().startswith("-")]


def best_note_line(question: str, notes: str) -> str:
    """Deterministic fallback: the note line sharing the most DISTINCTIVE words with the question.
    Words found in several note lines (e.g. 'HR', 'policy') count for less; a weak match returns ''."""
    from ..textutil import tokens

    lines = note_lines(notes)
    toks = [set(tokens(ln)) for ln in lines]
    q = {t for t in tokens(question) if t not in _GENERIC_Q and len(t) > 2}
    best, best_score = "", 0.0
    for ln, lt in zip(lines, toks):
        score = sum(1 / sum(t in other for other in toks) for t in q & lt)
        if score > best_score:
            best, best_score = ln, score
    return best if best_score >= 1.0 else ""


def generate_questions(ctx: RunContext, brief: str, inv: dict) -> QuestionList:
    msgs = prompts.split("intake_questions", brief=brief, inventory=inventory_text(inv))
    try:
        ql = ctx.llm.json(msgs, QuestionList, task="intake_questions", max_tokens=900)
    except LLMError as e:
        ctx.log(f"  ! question generation failed ({e}); proceeding with no questions", "yellow")
        ql = QuestionList(questions=[])
    # hard cap - the spec says at most 5, never trust the model to count
    seen, kept = set(), []
    for q in ql.questions:
        key = q.question.strip().lower()
        if key and key not in seen:
            seen.add(key)
            kept.append(q)
    ql.questions = kept[:MAX_QUESTIONS]
    return ql


def collect_answers(ctx: RunContext, ql: QuestionList) -> list[QAPair]:
    qa: list[QAPair] = []
    for i, q in enumerate(ql.questions, 1):
        answer, source = "", "default_assumption"
        if ctx.intake_mode == "interactive" and ctx.ask:
            reply = ctx.ask(f"Q{i}/{len(ql.questions)}: {q.question}\n   (why: {q.why_it_matters})\n"
                            f"   [Enter = assume: {q.default_assumption}]\n> ")
            if reply and reply.strip():
                answer, source = reply.strip(), "requester"
        elif ctx.intake_mode == "notes" and ctx.requester_notes.strip():
            lines = note_lines(ctx.requester_notes)
            numbered = "\n".join(f"{i}. {ln}" for i, ln in enumerate(lines, 1))
            msgs = prompts.split("intake_answer_from_notes", notes=numbered, question=q.question)
            try:  # picking a line number is far easier for a small model than writing the answer
                n = ctx.llm.json(msgs, _NoteLine, task="intake_answer_from_notes", max_tokens=40).line
                if 1 <= n <= len(lines):
                    answer, source = lines[n - 1], "requester_notes"
            except LLMError:
                pass
            if not answer:  # fallback only on a strong, distinctive word match
                line = best_note_line(q.question, ctx.requester_notes)
                if line:
                    answer, source = line, "requester_notes"
        if not answer:
            answer = q.default_assumption or "No preference stated."
        qa.append(QAPair(question=q.question, answer=answer, source=source))
        ctx.log(f"  Q{i}: {q.question}\n      A ({source}): {answer}")
    return qa


def write_requirements(ctx: RunContext, brief: str, inv: dict, qa: list[QAPair]) -> Requirements:
    qa_text = "\n".join(f"- Q: {p.question}\n  A [{p.source}]: {p.answer}" for p in qa) or "(no questions asked)"
    msgs = prompts.split("intake_requirements", brief=brief, qa=qa_text, inventory=inventory_text(inv))
    req = ctx.llm.json(msgs, Requirements, task="intake_requirements", max_tokens=1800, retries=3)
    req, restored = ensure_brief_coverage(ctx, brief, req)
    for r in restored:
        ctx.log(f"  + restored a request the requirements writer dropped: \"{r}\"", "yellow")
        req.assumptions.append(f"Restored from the brief by the coverage check: {r}")
    # a topic cannot be both answered and refused: small models sometimes copy refusals into must-answer
    from ..textutil import jaccard
    refuse = [t.topic for t in req.must_refuse_topics]
    req.must_answer_topics = [t for t in req.must_answer_topics
                              if not any(jaccard(t.topic, r) >= 0.5 for r in refuse)]
    # every default assumption must be visible in the document, even if the model forgot it
    for p in qa:
        if p.source == "default_assumption":
            line = f"Assumed (no reply): {p.question} -> {p.answer}"
            if line not in req.assumptions:
                req.assumptions.append(line)
    return req


def requirements_markdown(req: Requirements, qa: list[QAPair]) -> str:
    md = [f"# Requirements - {req.agent_name}", "", f"**Scope.** {req.scope}", "",
          f"**Audience.** {req.audience}  ", f"**Tone.** {req.tone}  ", f"**Language.** {req.language}  ",
          f"**Escalation contact.** {req.escalation_contact or '-'}", "", "## Must answer"]
    md += [f"- **{t.topic}** - {t.description}" for t in req.must_answer_topics]
    md += ["", "## Must refuse"] + [f"- **{t.topic}** - {t.reason}" for t in req.must_refuse_topics]
    if req.success_criteria:
        md += ["", "## Success criteria"] + [f"- {s}" for s in req.success_criteria]
    if req.constraints:
        md += ["", "## Constraints"] + [f"- {s}" for s in req.constraints]
    if req.assumptions:
        md += ["", "## Assumptions"] + [f"- {s}" for s in req.assumptions]
    md += ["", "## Intake interview"]
    md += [f"{i}. **{p.question}**  \n   {p.answer}  _(source: {p.source})_" for i, p in enumerate(qa, 1)]
    return "\n".join(md) + "\n"


def run_intake(ctx: RunContext, brief: str, inv: dict) -> tuple[Requirements, list[QAPair]]:
    ctx.stage("1. Intake interview")
    if ctx.preset_qa is not None:   # the UI asked the questions itself (same generator) before starting the run
        qa = [p if isinstance(p, QAPair) else QAPair.model_validate(p) for p in ctx.preset_qa][:MAX_QUESTIONS]
        ctx.save_json("01_intake/questions.json", {"questions": [{"question": p.question} for p in qa]})
        for i, p in enumerate(qa, 1):
            ctx.log(f"  Q{i}: {p.question}\n      A ({p.source}): {p.answer}")
    else:
        ql = generate_questions(ctx, brief, inv)
        ctx.save_json("01_intake/questions.json", ql)
        qa = collect_answers(ctx, ql)
    ctx.save_json("01_intake/transcript.json", [p.model_dump() for p in qa])
    req = write_requirements(ctx, brief, inv, qa)
    ctx.save_json("02_requirements/requirements_draft.json", req)
    ctx.save_text("02_requirements/requirements_draft.md", requirements_markdown(req, qa))
    ctx.log(f"  requirements: {len(req.must_answer_topics)} must-answer, {len(req.must_refuse_topics)} must-refuse topics")
    return req, qa
