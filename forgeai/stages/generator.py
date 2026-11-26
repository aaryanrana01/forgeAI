"""Requirement 3 - Agent generator.

requirements + documents -> declarative AgentDefinition:
  * tool selection: the model proposes with a quoted justification; the
    factory verifies the quote exists and the tool's deterministic
    precondition holds (veto otherwise)
  * retrieval parameters derived from document statistics (with rationale)
  * system prompt as patchable sections; N candidate styles for the tournament
  * output contract
"""

from __future__ import annotations

import json
import statistics

from ..schemas import BaseModel

from .. import prompts
from ..context import RunContext
from ..docs.loader import inventory_text
from ..llm import LLMError
from ..schemas import (AgentDefinition, GroundabilityReport, OutputContract, PromptSections, Requirements,
                       RetrievalConfig, ToolBinding)
from ..textutil import normalize, tokens
from ..tools.registry import REGISTRY, tool_catalog_text


class _Decision(BaseModel):
    tool: str
    attach: bool
    evidence_quote: str = ""
    justification: str = ""


class _Decisions(BaseModel):
    decisions: list[_Decision]


class _PromptDraft(BaseModel):
    role: str
    scope: str
    answering_rules: list[str]
    refusal_rules: list[str]
    tone_rules: list[str] = []
    tool_rules: list[str] = []
    format_rules: list[str] = []
    refusal_message: str


def needs_text(req: Requirements) -> str:
    """What the agent must actually DO - the only text that may justify a tool.
    Excludes the brief and the refuse list, so a request the groundability guard
    moved to 'refuse' (e.g. 'payroll calendar') can never pull in a tool."""
    lines = [f"- {t.topic}: {t.description}" for t in req.must_answer_topics]
    lines += [f"- {s}" for s in req.success_criteria]
    return "\n".join(lines)


def requirements_text(req: Requirements, *, include_refuse: bool = True) -> str:
    lines = [f"Agent: {req.agent_name}", f"Scope: {req.scope}", f"Audience: {req.audience}", f"Tone: {req.tone}",
             "Must answer:"] + [f"- {t.topic}: {t.description}" for t in req.must_answer_topics]
    if include_refuse:
        lines += ["Must refuse:"] + [f"- {t.topic}: {t.reason}" for t in req.must_refuse_topics]
    lines += [f"Constraint: {c}" for c in req.constraints] + [f"Success: {s}" for s in req.success_criteria]
    return "\n".join(lines)


def _quote_found(quote: str, haystack: str) -> bool:
    """Verbatim, or a close paraphrase of ONE requirement line (small models rarely copy perfectly)."""
    q = normalize(quote)
    if len(q) < 4:
        return False
    if q in normalize(haystack):
        return True
    qt = set(tokens(quote))
    if not qt:
        return False
    best = max((len(qt & set(tokens(line))) / len(qt) for line in haystack.splitlines() if line.strip()), default=0)
    return best >= 0.6


def _rule_need(name: str, req: Requirements, docs) -> str:
    """Deterministic evidence that a tool is needed, from the requirements AND the data structure:
    csv_lookup when a must-answer topic is about a CSV's columns; calculator / current_date when a
    must-answer topic is computed from a numeric price / lead-time column. Returns the reason or ''."""
    from ..docs.loader import table_computable, table_match

    for t in req.must_answer_topics:
        text = f"{t.topic} {t.description}"
        if name == "csv_lookup":
            table, cols = table_match(text, docs)
            if table:
                return f"must-answer topic '{t.topic}' needs exact values from {table} (columns: {', '.join(cols)})"
            ctable, _ = table_computable(t.topic, docs)
            if ctable:
                return f"must-answer topic '{t.topic}' is computed from {ctable}, so rows must be looked up first"
        elif name in ("calculator", "current_date"):
            ctable, tool = table_computable(t.topic, docs)
            if ctable and tool == name:
                return f"must-answer topic '{t.topic}' is computed from {ctable} columns"
    return ""


# ------------------------------------------------------------------ tools
def select_tools(ctx: RunContext, req: Requirements, brief: str, docs, inv: dict) -> tuple[list[ToolBinding], list[dict]]:
    need_text = needs_text(req)
    refuse = "\n".join(f"- {t.topic}" for t in req.must_refuse_topics) or "(none)"
    try:
        res = ctx.llm.json(prompts.split("tool_selection", requirements=need_text, refuse=refuse,
                                         inventory=inventory_text(inv), tools=tool_catalog_text()),
                           _Decisions, task="tool_selection", max_tokens=700)
        decisions = {d.tool: d for d in res.decisions if d.tool in REGISTRY}
    except LLMError as e:
        ctx.log(f"  ! tool selection failed ({e}); asking tool by tool", "yellow")
        decisions = {}
    # Small models often return a decision for only one or two tools. Ask again, ONE tool at a time
    # (a much easier question), for every tool the model skipped whose precondition could hold.
    for name, tool in REGISTRY.items():
        if name in decisions or not tool.precondition(need_text, docs)[0]:
            continue
        try:
            one = ctx.llm.json(prompts.split("tool_check", requirements=need_text, refuse=refuse, tool=name,
                                             description=tool.description, when=tool.when_to_use),
                               _Decision, task="tool_check", max_tokens=250)
            one.tool = name
            decisions[name] = one
            ctx.log(f"  (asked again about {name}: attach={one.attach})")
        except LLMError:
            pass

    bindings, audit = [], []
    for name, tool in REGISTRY.items():
        d = decisions.get(name)
        pre_ok, pre_why = tool.precondition(need_text, docs)
        entry = {"tool": name, "model_attach": bool(d and d.attach), "model_quote": d.evidence_quote if d else "",
                 "model_justification": d.justification if d else "(no decision returned)",
                 "precondition_ok": pre_ok, "precondition": pre_why}
        if d and d.attach:
            quote_ok = _quote_found(d.evidence_quote, need_text)
            entry["quote_verified"] = quote_ok
            if not pre_ok:
                entry["final"], entry["why"] = False, f"VETOED: precondition failed ({pre_why})"
            elif not quote_ok:
                entry["final"], entry["why"] = False, "VETOED: evidence quote not found in requirements (invented need)"
            else:
                entry["final"], entry["why"] = True, "attached: model justified it and precondition holds"
        else:
            entry["final"], entry["why"] = False, "not requested by model"
        # the data structure can prove a need the small model missed (never used for weather)
        rule = _rule_need(name, req, docs) if pre_ok and name != "weather" else ""
        if not entry["final"] and rule:
            entry["final"] = True
            entry["why"] = f"attached by rule ({entry['why']}): {rule}"
            d = d or _Decision(tool=name, attach=True)
            d.justification = d.justification or rule
        if entry["final"]:
            cfg = {}
            if name == "csv_lookup":
                csvs = [x for x in docs if x.kind == "csv"]
                cfg = {"files": [x.doc_id for x in csvs], "columns": {x.doc_id: x.columns for x in csvs}}
            bindings.append(ToolBinding(name=name, config=cfg, justification=d.justification,
                                        evidence_quote=d.evidence_quote))
        audit.append(entry)
        ctx.log(f"  {'+' if entry['final'] else '-'} {name}: {entry['why']}")
    return bindings, audit


# -------------------------------------------------------------- retrieval
def initial_retrieval(docs, embed_model: str) -> RetrievalConfig:
    text_docs = [d for d in docs if d.kind != "csv"]
    from ..retrieval.chunker import _paragraphs
    para_lens = [len(p.split()) for d in text_docs for page in (d.pages or [d.text]) for p in _paragraphs(page)
                 if len(p.split()) > 8]
    med = statistics.median(para_lens) if para_lens else 120
    chunk = int(min(260, max(120, med * 2.5)))
    n_docs = len(docs)
    top_k = 5 if n_docs <= 3 else 6
    mode = "hybrid" if embed_model else "bm25"
    return RetrievalConfig(
        chunk_size=chunk, chunk_overlap=max(20, chunk // 5), prepend_headings=True, top_k=top_k, mode=mode,
        query_expansion=False, min_relevance=0.0,
        rationale=(f"median paragraph {med:.0f} words -> chunk {chunk} words (~2-3 paragraphs) with 20% overlap; "
                   f"{n_docs} documents -> top_k {top_k}; section headings prefixed so keyword search sees "
                   f"the section a chunk came from; mode={mode}" + ("" if embed_model else " (no embedding model configured)")))


# ----------------------------------------------------------------- prompts
STYLES = {}
for line in (prompts.DIR / "prompt_style_variants.md").read_text().splitlines():
    if ":" in line:
        k, v = line.split(":", 1)
        STYLES[k.strip()] = v.strip()

BASE_RULES = [
    "Use only facts found in the CONTEXT and TOOL RESULTS sections. Never use outside knowledge.",
    "If the CONTEXT does not contain the answer, set refused=true. Do not guess.",
]


def draft_prompt(ctx: RunContext, req: Requirements, gr: GroundabilityReport, tools: list[ToolBinding],
                 style: str) -> tuple[PromptSections, str]:
    gaps = "\n".join(f"- NOT COVERED: {g}" for g in gr.flagged_gaps) or "(all requested topics are covered)"
    msgs = prompts.split("prompt_writer", requirements=requirements_text(req), gaps=gaps,
                         tools=", ".join(t.name for t in tools) or "none", style=STYLES.get(style, style),
                         contact=req.escalation_contact or "the relevant team")
    try:
        p = ctx.llm.json(msgs, _PromptDraft, task=f"prompt_writer_{style}", max_tokens=1400, retries=3)
    except LLMError as e:
        ctx.log(f"  ! prompt writer failed for style {style} ({e}); using fallback template", "yellow")
        p = _PromptDraft(
            role=f"You are {req.agent_name}, an assistant for {req.audience}.", scope=req.scope,
            answering_rules=["Cite the ids of the passages you used.", "Copy numbers and dates exactly."],
            refusal_rules=[f"Refuse questions about {t.topic}." for t in req.must_refuse_topics],
            tone_rules=[f"Tone: {req.tone}."], format_rules=["Keep answers short."],
            refusal_message=f"Sorry, I can't help with that. Please contact {req.escalation_contact or 'the relevant team'}.")
    sections = PromptSections(role=p.role, scope=p.scope, answering_rules=p.answering_rules,
                              refusal_rules=p.refusal_rules, tone_rules=p.tone_rules,
                              tool_rules=p.tool_rules if tools else [], format_rules=p.format_rules)
    # non-negotiable grounding rules are guaranteed present (not left to the model)
    for r in reversed(BASE_RULES):
        if not any(normalize(r)[:40] in normalize(x) for x in sections.answering_rules):
            sections.answering_rules.insert(0, r)
    if tools and not sections.tool_rules:
        sections.tool_rules = [f"Use {t.name} when needed: {REGISTRY[t.name].when_to_use}" for t in tools]
    return sections, p.refusal_message


def build_definition(req: Requirements, sections: PromptSections, refusal_message: str, tools: list[ToolBinding],
                     retrieval: RetrievalConfig, gr: GroundabilityReport, meta: dict) -> AgentDefinition:
    from ..runtime.agent import render_system_prompt

    refuse = [t.topic for t in req.must_refuse_topics]
    words = 120 if any(w in req.tone.lower() for w in ("concise", "brief", "short")) else 180
    d = AgentDefinition(
        name=req.agent_name, version=0, description=req.scope, prompt=sections, refusal_message=refusal_message,
        must_refuse_topics=refuse, retrieval=retrieval, tools=tools,
        output_contract=OutputContract(max_answer_words=words), temperature=0.0, generated_by=meta)
    d.system_prompt = render_system_prompt(sections, d)
    return d


def run_generator(ctx: RunContext, req: Requirements, gr: GroundabilityReport, brief: str, docs, inv: dict,
                  n_candidates: int = 3) -> tuple[list[AgentDefinition], list[dict]]:
    ctx.stage("3. Agent generator")
    tools, audit = select_tools(ctx, req, brief, docs, inv)
    ctx.save_json("03_agent/tool_selection.json", audit)
    retrieval = initial_retrieval(docs, ctx.settings.embed_model)
    ctx.log(f"  retrieval: {retrieval.rationale}")
    styles = list(STYLES)[: max(1, n_candidates)]
    cands = []
    for style in styles:
        sections, refusal_msg = draft_prompt(ctx, req, gr, tools, style)
        meta = {"factory_model": ctx.settings.model, "prompt_style": style,
                "prompt_fingerprints": prompts.fingerprint("prompt_writer", "tool_selection")}
        d = build_definition(req, sections, refusal_msg, tools, retrieval, gr, meta)
        cands.append(d)
        ctx.save_json(f"03_agent/candidates/{style}.json", d)
        ctx.log(f"  drafted prompt candidate '{style}' ({len(d.system_prompt.split())} words)")
    return cands, audit


def definition_diff(a: AgentDefinition, b: AgentDefinition) -> dict:
    """Small structural diff used in iteration logs."""
    da, db = json.loads(a.model_dump_json()), json.loads(b.model_dump_json())
    out = {}
    for key in ("retrieval", "prompt", "must_refuse_topics", "temperature", "refusal_message", "tools"):
        if da.get(key) != db.get(key):
            if isinstance(da.get(key), dict):
                out[key] = {k: {"before": da[key].get(k), "after": db[key].get(k)}
                            for k in set(da[key]) | set(db[key]) if da[key].get(k) != db[key].get(k)}
            else:
                out[key] = {"before": da.get(key), "after": db.get(key)}
    return out
