"""Requirement 8 - minimal generic chat runner. Loads ANY produced definition."""

from __future__ import annotations

import json
from pathlib import Path

from ..config import Budget, Settings
from ..llm import LLM, Meter, default_responder
from .agent import AgentRuntime, load_definition


def chat_loop(definition_path: str | Path, *, settings: Settings | None = None, show_json: bool = False,
              once: str | None = None) -> None:
    settings = settings or Settings()
    d, kdir = load_definition(definition_path)
    llm = LLM(settings, Meter(Budget()), responder=default_responder(settings))
    rt = AgentRuntime(d, kdir, llm, embed_model=settings.embed_model)
    print(f"\n{d.name} (definition v{d.version}) - {d.description}")
    print(f"knowledge: {kdir}  |  tools: {[t.name for t in d.tools] or 'none'}  |  model: {settings.model}")
    print("Type a question. Commands: /quit, /json (toggle raw output), /reset\n")
    history: list[dict] = []
    while True:
        if once is not None:
            q = once
        else:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
        if not q:
            continue
        if q in ("/quit", "/exit"):
            break
        if q == "/json":
            show_json = not show_json
            print(f"(raw output {'on' if show_json else 'off'})")
            continue
        if q == "/reset":
            history = []
            print("(conversation cleared)")
            continue
        r = rt.answer(q, history=history)
        print(f"\n{d.name}> {r.answer}")
        if r.citations:
            print(f"   sources: {', '.join(r.citations)}")
        if r.tool_calls:
            print("   tools: " + "; ".join(f"{t['tool']}({json.dumps(t['args'])})" for t in r.tool_calls))
        if not r.contract_valid:
            print(f"   ! contract issues: {r.contract_errors}")
        if show_json:
            print(json.dumps(r.to_dict(), indent=2, ensure_ascii=False))
        print()
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": r.answer}]
        if once is not None:
            break
