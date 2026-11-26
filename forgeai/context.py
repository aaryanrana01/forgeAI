"""Shared run context passed to every stage."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .config import Settings
from .llm import LLM, Meter


def _console():
    try:
        from rich.console import Console
        return Console(highlight=False)
    except ImportError:  # pragma: no cover
        return None


@dataclass
class RunContext:
    settings: Settings
    meter: Meter
    llm: LLM                     # factory model
    judge: LLM                   # judge model (ideally a different family)
    out_dir: Path
    # how the intake interviewer gets answers: interactive | notes | unattended
    intake_mode: str = "unattended"
    requester_notes: str = ""
    ask: Callable[[str], str] | None = None          # interactive question callback
    approve: Callable[[Path], bool] | None = None    # human checkpoint callback
    log_fn: Callable[[str], None] | None = None      # UI log sink
    preset_qa: list | None = None                    # UI: questions already asked and answered
    events: list[dict] = field(default_factory=list)
    _console: Any = field(default_factory=_console)

    def log(self, msg: str, style: str = "") -> None:
        if self.log_fn:
            self.log_fn(msg)
        if self._console is not None:
            self._console.print(f"[{style}]{msg}[/{style}]" if style else msg)
        else:  # pragma: no cover
            print(msg)

    def stage(self, title: str) -> None:
        self.events.append({"stage": title, "tokens": self.meter.total_tokens, "t": round(self.meter.elapsed, 1)})
        self.log(f"\n━━ {title} ━━", "bold cyan")

    def path(self, rel: str) -> Path:
        p = self.out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save_json(self, rel: str, obj: Any) -> Path:
        p = self.path(rel)
        if isinstance(obj, BaseModel):
            p.write_text(obj.model_dump_json(indent=2))
        else:
            p.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=_default))
        return p

    def save_text(self, rel: str, text: str) -> Path:
        p = self.path(rel)
        p.write_text(text)
        return p


def _default(o):
    if isinstance(o, BaseModel):
        return o.model_dump()
    if isinstance(o, Path):
        return str(o)
    if isinstance(o, set):
        return sorted(o)
    if isinstance(o, tuple):
        return list(o)
    return str(o)
