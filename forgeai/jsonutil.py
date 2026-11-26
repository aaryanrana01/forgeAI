"""Robust JSON handling for small models that wrap JSON in prose or code fences,
leave trailing commas, or emit single quotes."""

from __future__ import annotations

import json
import re
from typing import Any


class JSONExtractError(ValueError):
    pass


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _balanced_candidates(text: str) -> list[str]:
    """Return every balanced {...} or [...] block, longest first."""
    out = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        out.append(text[start : i + 1])
                        break
            start = text.find(opener, start + 1)
    return sorted(out, key=len, reverse=True)


def _repair(s: str) -> str:
    s = re.sub(r",\s*([}\]])", r"\1", s)  # trailing commas
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    s = re.sub(r"\bTrue\b", "true", s)
    s = re.sub(r"\bFalse\b", "false", s)
    s = re.sub(r"\bNone\b", "null", s)
    return s


def extract_json(text: str) -> Any:
    """Best-effort extraction of the first JSON value from model output."""
    if text is None:
        raise JSONExtractError("empty output")
    text = text.strip()
    attempts = [text]
    attempts += [m.strip() for m in _FENCE.findall(text)]
    attempts += _balanced_candidates(text)
    for cand in attempts:
        for variant in (cand, _repair(cand)):
            try:
                return json.loads(variant)
            except (json.JSONDecodeError, TypeError):
                continue
    raise JSONExtractError(f"no valid JSON found in output: {text[:200]!r}")


def inline_refs(schema: dict) -> dict:
    """Inline $ref/$defs so grammar-constrained decoders (Ollama/llama.cpp)
    get a flat schema."""
    defs = schema.get("$defs", {}) or schema.get("definitions", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                return resolve(defs.get(name, {}))
            return {k: resolve(v) for k, v in node.items() if k not in ("$defs", "definitions")}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def require_all(schema: dict) -> dict:
    """Mark every property as required (recursively) for grammar-constrained decoding, so a small model
    cannot silently drop a field like `citations`. Validation itself stays lenient (pydantic defaults)."""
    if isinstance(schema, dict):
        if schema.get("type") == "object" and "properties" in schema:
            schema["required"] = list(schema["properties"])
        for v in schema.values():
            if isinstance(v, (dict, list)):
                require_all(v)
    elif isinstance(schema, list):
        for v in schema:
            require_all(v)
    return schema
