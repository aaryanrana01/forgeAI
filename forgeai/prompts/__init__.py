"""All factory prompts live in this folder as markdown files (they are part of
the deliverable: the eval set is generated, and these are its generation
prompts). Variables use $name syntax so JSON braces need no escaping."""

from __future__ import annotations

import hashlib
from pathlib import Path
from string import Template

DIR = Path(__file__).parent


def load(name: str, **vars) -> str:
    text = (DIR / f"{name}.md").read_text()
    return Template(text).safe_substitute(**{k: str(v) for k, v in vars.items()})


def split(name: str, **vars) -> list[dict]:
    """Prompt files contain '### SYSTEM' and '### USER' sections."""
    text = load(name, **vars)
    if "### USER" not in text:
        return [{"role": "user", "content": text.strip()}]
    sys_part, user_part = text.split("### USER", 1)
    sys_part = sys_part.replace("### SYSTEM", "").strip()
    msgs = []
    if sys_part:
        msgs.append({"role": "system", "content": sys_part})
    msgs.append({"role": "user", "content": user_part.strip()})
    return msgs


def fingerprint(*names: str) -> dict[str, str]:
    return {n: hashlib.sha256((DIR / f"{n}.md").read_bytes()).hexdigest()[:12] for n in names}
