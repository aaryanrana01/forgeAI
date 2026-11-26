"""Generic agent runtime: loads ANY definition produced by the factory and runs it.

Flow per question:
  1. retrieve top-k chunks from the definition's knowledge folder
  2. (only if tools are attached) up to N planner steps: call a tool or stop
  3. answer step, constrained to the output contract (JSON)
  4. deterministic contract validation; one repair retry; violations recorded
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..schemas import BaseModel

from ..docs.loader import load_folder
from ..llm import LLM, LLMError
from ..retrieval.index import Retriever
from ..schemas import AgentDefinition, PromptSections
from ..textutil import looks_like_refusal
from ..tools.registry import build_tools

MAX_TOOL_STEPS = 3


class AgentAnswer(BaseModel):
    answer: str
    citations: list[str] = []
    refused: bool = False
    refusal_reason: str = ""


class ToolStep(BaseModel):
    action: Literal["call_tool", "answer"]
    tool: str = ""
    args: dict = {}
    reason: str = ""


@dataclass
class AgentResponse:
    answer: str
    citations: list[str]
    refused: bool
    refusal_reason: str
    retrieved_ids: list[str]
    tool_calls: list[dict] = field(default_factory=list)
    contract_valid: bool = True
    contract_errors: list[str] = field(default_factory=list)
    context_text: str = ""
    latency_s: float = 0.0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "context_text"}


def render_system_prompt(p: PromptSections, d: AgentDefinition | None = None) -> str:
    def block(title: str, rules: list[str]) -> str:
        return f"\n## {title}\n" + "\n".join(f"- {r}" for r in rules) if rules else ""

    text = f"{p.role.strip()}\n\n## Scope\n{p.scope.strip()}"
    text += block("How to answer", p.answering_rules)
    refusal = list(p.refusal_rules)
    if d is not None:
        if d.must_refuse_topics:
            refusal.append("Always refuse these topics: " + "; ".join(d.must_refuse_topics))
        refusal.append(f'When you refuse, set "refused": true and use this message: "{d.refusal_message}"')
    text += block("When to refuse", refusal)
    text += block("Tone", p.tone_rules)
    text += block("Tools", p.tool_rules)
    fmt = list(p.format_rules)
    if d is not None:
        fmt += [f"Keep the answer under {d.output_contract.max_answer_words} words."]
        fmt += d.output_contract.rules
        fmt.append('Reply ONLY with JSON: {"answer": str, "citations": [ids], "refused": bool, "refusal_reason": str}')
    text += block("Output format", fmt)
    return text.strip()


def load_definition(path: str | Path) -> tuple[AgentDefinition, Path]:
    path = Path(path)
    d = AgentDefinition.model_validate_json(path.read_text())
    kdir = (path.parent / d.knowledge_dir).resolve()
    if not kdir.exists():  # definitions inside definitions/ point one level up
        alt = (path.parent.parent / d.knowledge_dir).resolve()
        kdir = alt if alt.exists() else kdir
    return d, kdir


class AgentRuntime:
    def __init__(self, definition: AgentDefinition, knowledge_dir: str | Path, llm: LLM,
                 embed_model: str = "", docs=None, today=None):
        self.d = definition
        self.knowledge_dir = Path(knowledge_dir)
        self.llm = llm
        self.docs = docs if docs is not None else load_folder(self.knowledge_dir)
        self.retriever = Retriever(self.docs, definition.retrieval, llm=llm, embed_model=embed_model,
                                   cache_dir=llm.settings.cache_dir)
        self.tools = build_tools(definition.tools)
        self.system_prompt = render_system_prompt(definition.prompt, definition)
        self.today = today

    # ------------------------------------------------------------ tools
    def _tool_menu(self) -> str:
        lines = []
        for name, (tool, cfg) in self.tools.items():
            extra = ""
            if name == "csv_lookup":
                extra = f" Tables: {json.dumps(cfg.get('columns', {}))}"
            lines.append(f"- {name}: {tool.description} Arguments: {json.dumps(tool.input_schema)}.{extra}")
        return "\n".join(lines)

    def _run_tools(self, question: str, context: str, history_text: str) -> list[dict]:
        calls: list[dict] = []
        for step in range(MAX_TOOL_STEPS):
            done = "\n".join(f"[tool:{c['tool']}#{i + 1}] args={json.dumps(c['args'])} -> {json.dumps(c['result'])[:900]}"
                             for i, c in enumerate(calls)) or "(none yet)"
            msgs = [
                {"role": "system", "content": (
                    "You are the tool planner for an assistant. Decide the NEXT single step: call one tool, "
                    "or answer if the context and tool results already contain everything needed. "
                    "Never invent tool names. Use calculator for any arithmetic instead of doing it yourself. "
                    "Use csv_lookup to fetch exact values from tables before calculating with them.\n"
                    f"Available tools:\n{self._tool_menu()}\n" + "\n".join(f"- {r}" for r in self.d.prompt.tool_rules))},
                {"role": "user", "content": (
                    f"{history_text}QUESTION: {question}\n\nDOCUMENT CONTEXT (may already contain the answer):\n"
                    f"{context[:3500]}\n\nTOOL RESULTS SO FAR:\n{done}\n\n"
                    'Return {"action": "call_tool" or "answer", "tool": name, "args": {...}, "reason": short}')},
            ]
            try:
                st = self.llm.json(msgs, ToolStep, task="agent_tool_plan", max_tokens=250)
            except LLMError:
                break
            if st.action != "call_tool" or st.tool not in self.tools:
                break
            if any(c["tool"] == st.tool and c["args"] == st.args for c in calls):
                break  # repeated identical call -> stop looping
            tool, cfg = self.tools[st.tool]
            result = tool.run(st.args, {"config": cfg, "knowledge_dir": str(self.knowledge_dir),
                                        "today": self.today})
            calls.append({"tool": st.tool, "args": st.args, "result": result, "reason": st.reason})
        return calls

    # ---------------------------------------------------------- answer
    def answer(self, question: str, history: list[dict] | None = None) -> AgentResponse:
        t0 = time.time()
        search_q = question
        if history and len(question.split()) < 8:  # short follow-up ("and for M3?") -> reuse the last user turn
            last_user = next((t["content"] for t in reversed(history) if t["role"] == "user"), "")
            search_q = f"{last_user} {question}"
        hits = self.retriever.search(search_q)
        context = "\n\n".join(c.render() for c, _ in hits) or "(no relevant passages found)"
        retrieved_ids = [c.chunk_id for c, _ in hits]
        history_text = ""
        if history:
            turns = history[-6:]
            history_text = "CONVERSATION SO FAR:\n" + "\n".join(
                f"{t['role'].upper()}: {t['content'][:400]}" for t in turns) + "\n\n"

        tool_calls = self._run_tools(question, context, history_text) if self.tools else []
        tool_ids = [f"tool:{c['tool']}#{i + 1}" for i, c in enumerate(tool_calls)]
        tool_text = "\n".join(f"[{tid}] {json.dumps(c['result'], ensure_ascii=False)[:1500]}"
                              for tid, c in zip(tool_ids, tool_calls))
        user = (f"CONTEXT:\n{context}\n\n" + (f"TOOL RESULTS:\n{tool_text}\n\n" if tool_text else "")
                + f"{history_text}QUESTION: {question}")
        msgs = [{"role": "system", "content": self.system_prompt}, {"role": "user", "content": user}]
        valid_ids = set(retrieved_ids) | set(tool_ids)

        errors: list[str] = []
        parsed: AgentAnswer | None = None
        for attempt in range(2):
            try:
                parsed = self.llm.json(msgs, AgentAnswer, task="agent_answer",
                                       temperature=self.d.temperature, max_tokens=600)
            except LLMError as e:
                errors = [f"no valid JSON: {e}"]
                parsed = None
                break
            errors = self._validate(parsed, valid_ids)
            if not errors:
                break
            if attempt == 0:  # one repair round with the concrete contract violations
                msgs = msgs + [
                    {"role": "assistant", "content": parsed.model_dump_json()},
                    {"role": "user", "content": "Your reply broke the output contract: " + "; ".join(errors)
                     + f". Valid citation ids are: {sorted(valid_ids)}. Reply again with corrected JSON."}]

        if parsed is None:
            return AgentResponse("(agent failed to produce a valid response)", [], False, "", retrieved_ids,
                                 tool_calls, False, errors, context + "\n" + tool_text, time.time() - t0)

        citations = [c for c in parsed.citations if c in valid_ids]
        answer = parsed.answer.strip()
        if parsed.refused and self.d.refusal_message and self.d.refusal_message[:40].lower() not in answer.lower():
            answer = (answer + " " + self.d.refusal_message).strip() if answer else self.d.refusal_message
        return AgentResponse(answer, citations, parsed.refused, parsed.refusal_reason, retrieved_ids, tool_calls,
                             not errors, errors, context + "\n" + tool_text, time.time() - t0)

    def _validate(self, a: AgentAnswer, valid_ids: set[str]) -> list[str]:
        errs = []
        if not a.answer.strip():
            errs.append("answer is empty")
        bad = [c for c in a.citations if c not in valid_ids]
        if bad:
            errs.append(f"citations not in context: {bad}")
        if not a.refused and not [c for c in a.citations if c in valid_ids]:
            errs.append("refused is false but no valid citation given")
        if not a.refused and looks_like_refusal(a.answer) and len(a.answer.split()) < 40:
            errs.append("answer reads as a refusal but refused=false")
        if len(a.answer.split()) > self.d.output_contract.max_answer_words * 1.5:
            errs.append(f"answer longer than {self.d.output_contract.max_answer_words} words")
        return errs
