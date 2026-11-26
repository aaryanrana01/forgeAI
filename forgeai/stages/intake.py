"""Requirement 1 - Intake interviewer.

brief + document inventory -> <=5 clarifying questions -> answers (live CLI,
the requester's written notes, or explicit default assumptions) -> structured
requirements document (JSON + Markdown)."""

from __future__ import annotations

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..docs.loader import inventory_text
from ..llm import LLMError
from ..schemas import QAPair, QuestionList, Requirements

MAX_QUESTIONS = 5


class _NoteAnswer(BaseModel):
    answer: str


# words that appear in almost every intake question, so they cannot identify the matching note line
_GENERIC_Q = {"assistant", "user", "staff", "shore", "respons", "response", "question", "expect", "specific", "provid",
              "any", "there", "should", "would", "will", "help", "need", "employee", "interact", "regard",
              "handle", "ensure", "follow", "aware", "appropriately", "primary", "exactly"}


def best_note_line(question: str, notes: str) -> str:
    """Deterministic fallback: the notes bullet sharing the most distinctive words with the question."""
    from ..textutil import tokens

    q = {t for t in tokens(question) if t not in _GENERIC_Q and len(t) > 2}
    best, best_n = "", 0
    for ln in notes.splitlines():
        ln = ln.strip()
        if not ln.startswith("-"):
            continue
        n = len(q & set(tokens(ln)))
        if n > best_n:
            best, best_n = ln.lstrip("- ").strip(), n
    return best if best_n >= 1 else ""


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
            msgs = prompts.split("intake_answer_from_notes", notes=ctx.requester_notes, question=q.question)
            try:
                a = ctx.llm.json(msgs, _NoteAnswer, task="intake_answer_from_notes", max_tokens=200).answer
                if a.strip() and "NOT_IN_NOTES" not in a:
                    answer, source = a.strip(), "requester_notes"
            except LLMError:
                pass
            if not answer:  # small models often miss an answer that is plainly in the notes
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
