"""LLM client used by every stage.

* Talks to Ollama (local open models) or any OpenAI-compatible server.
* Structured output: pydantic schema -> grammar-constrained decoding on Ollama,
  JSON mode elsewhere, plus a parse -> validate -> repair-retry loop, because
  small models still break JSON now and then.
* Every call is metered (tokens, latency, calls) against the run budget and
  logged to llm_calls.jsonl, so cost claims in the report are evidence.
* Deterministic disk cache (temperature 0 + fixed seed) makes reruns cheap.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from .config import Budget, Settings
from .jsonutil import JSONExtractError, extract_json, inline_refs, require_all

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


class PlaceholderCopied(ValueError):
    pass


class Meter:
    """Shared usage meter for a run (factory model + judge model + embeddings)."""

    def __init__(self, budget: Budget | None = None, log_path: Path | None = None):
        self.budget = budget or Budget()
        self.log_path = log_path
        self.started = time.time()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.calls = 0
        self.cached_calls = 0
        self.by_task: dict[str, dict[str, float]] = {}

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def check(self) -> None:
        b = self.budget
        if self.total_tokens > b.max_tokens:
            raise BudgetExceeded(f"token budget exhausted ({self.total_tokens} > {b.max_tokens})")
        if self.elapsed > b.max_seconds:
            raise BudgetExceeded(f"time budget exhausted ({self.elapsed:.0f}s > {b.max_seconds}s)")
        if self.calls > b.max_llm_calls:
            raise BudgetExceeded(f"call budget exhausted ({self.calls} > {b.max_llm_calls})")

    def remaining_tokens(self) -> int:
        return self.budget.max_tokens - self.total_tokens

    def record(self, *, task: str, model: str, prompt_tokens: int, completion_tokens: int,
               latency: float, cached: bool, ok: bool = True) -> None:
        if cached:
            self.cached_calls += 1
        else:
            self.calls += 1
            self.prompt_tokens += prompt_tokens
            self.completion_tokens += completion_tokens
        t = self.by_task.setdefault(task, {"calls": 0, "tokens": 0, "seconds": 0.0, "cached": 0})
        t["calls"] += 1
        t["cached"] += int(cached)
        t["tokens"] += 0 if cached else prompt_tokens + completion_tokens
        t["seconds"] += latency
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(json.dumps({
                    "ts": round(time.time(), 2), "task": task, "model": model,
                    "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                    "latency_s": round(latency, 2), "cached": cached, "ok": ok,
                }) + "\n")

    def snapshot(self) -> dict[str, Any]:
        return {
            "llm_calls": self.calls,
            "cached_calls": self.cached_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_seconds": round(self.elapsed, 1),
            "budget": {
                "max_tokens": self.budget.max_tokens,
                "max_seconds": self.budget.max_seconds,
                "max_llm_calls": self.budget.max_llm_calls,
            },
            "by_task": {k: {kk: round(vv, 1) for kk, vv in v.items()} for k, v in sorted(self.by_task.items())},
        }


PLACEHOLDERS = {"string", "str", "text", "...", "<string>", "<text>", "string | null"}


def find_placeholders(data: Any, path: str = "") -> list[str]:
    """Small models sometimes copy the example shape literally ({"answer": "string"}).
    Return the paths of fields whose value is just a placeholder word."""
    out: list[str] = []
    if isinstance(data, dict):
        for k, v in data.items():
            out += find_placeholders(v, f"{path}.{k}" if path else k)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out += find_placeholders(v, f"{path}[{i}]")
    elif isinstance(data, str) and data.strip().lower() in PLACEHOLDERS:
        out.append(path or "value")
    return out


def schema_shape(schema: dict) -> Any:
    """Turn a JSON schema into a compact example skeleton that a small model can
    imitate, e.g. {"questions": [{"question": "string"}]}."""
    t = schema.get("type")
    if "anyOf" in schema:
        non_null = [s for s in schema["anyOf"] if s.get("type") != "null"]
        return schema_shape(non_null[0]) if non_null else None
    if "enum" in schema:
        return " | ".join(map(str, schema["enum"]))
    if t == "object":
        return {k: schema_shape(v) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [schema_shape(schema.get("items", {}))]
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return True
    return "string"


Responder = Callable[[str, list[dict], dict | None], str]


class LLM:
    def __init__(self, settings: Settings, meter: Meter, *, model: str | None = None,
                 responder: Responder | None = None):
        self.settings = settings
        self.meter = meter
        self.model = model or settings.model
        self.responder = responder  # only for backend == "fake"
        self.cache_dir = Path(settings.cache_dir)
        if settings.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ core
    def _cache_key(self, payload: dict) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:32]

    def chat(self, messages: list[dict], *, task: str, temperature: float = 0.0,
             schema: dict | None = None, max_tokens: int = 1024) -> str:
        self.meter.check()
        payload = {"backend": self.settings.backend, "model": self.model, "messages": messages,
                   "schema": schema, "temperature": temperature, "seed": self.settings.seed,
                   "max_tokens": max_tokens}
        key = self._cache_key(payload)
        cache_file = self.cache_dir / f"{key}.json"
        if self.settings.use_cache and self.settings.backend != "fake" and cache_file.exists():
            data = json.loads(cache_file.read_text())
            self.meter.record(task=task, model=self.model, prompt_tokens=data.get("pt", 0),
                              completion_tokens=data.get("ct", 0), latency=0.0, cached=True)
            return data["content"]

        t0 = time.time()
        if self.settings.backend == "ollama":
            content, pt, ct = self._ollama(messages, temperature, schema, max_tokens)
        elif self.settings.backend == "openai":
            content, pt, ct = self._openai(messages, temperature, schema, max_tokens)
        elif self.settings.backend == "fake":
            if self.responder is None:
                raise LLMError("fake backend needs a responder")
            content = self.responder(task, messages, schema)
            pt = sum(len(m["content"]) for m in messages) // 4
            ct = len(content) // 4
        else:
            raise LLMError(f"unknown backend {self.settings.backend!r}")
        latency = time.time() - t0
        self.meter.record(task=task, model=self.model, prompt_tokens=pt, completion_tokens=ct,
                          latency=latency, cached=False)
        if self.settings.use_cache and self.settings.backend != "fake":
            cache_file.write_text(json.dumps({"content": content, "pt": pt, "ct": ct}))
        return content

    def _ollama(self, messages, temperature, schema, max_tokens):
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": temperature, "seed": self.settings.seed,
                        "num_ctx": self.settings.num_ctx, "num_predict": max_tokens},
        }
        if schema is not None:
            body["format"] = schema
        last_err = None
        for attempt in range(3):
            try:
                r = requests.post(f"{self.settings.base_url}/api/chat", json=body,
                                  timeout=self.settings.timeout)
                if r.status_code == 404 and "not found" in r.text.lower():
                    raise LLMError(f"Ollama model '{self.model}' not found. Run: ollama pull {self.model}")
                r.raise_for_status()
                data = r.json()
                return (data["message"]["content"], data.get("prompt_eval_count", 0) or 0,
                        data.get("eval_count", 0) or 0)
            except LLMError:
                raise
            except requests.ConnectionError as e:
                raise LLMError(
                    f"Cannot reach Ollama at {self.settings.base_url}. Is `ollama serve` running?"
                ) from e
            except Exception as e:  # timeouts, 5xx
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"Ollama call failed: {last_err}")

    def _openai(self, messages, temperature, schema, max_tokens):
        body: dict[str, Any] = {"model": self.model, "messages": messages,
                                "temperature": temperature, "max_tokens": max_tokens,
                                "seed": self.settings.seed}
        if schema is not None:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.settings.api_key}"} if self.settings.api_key else {}
        last_err = None
        for attempt in range(5):
            try:
                r = requests.post(f"{self.settings.base_url.rstrip('/')}/chat/completions",
                                  json=body, headers=headers, timeout=self.settings.timeout)
                if r.status_code == 429:  # free tiers rate-limit: back off
                    wait = float(r.headers.get("retry-after", 5 * (attempt + 1)))
                    time.sleep(min(wait, 60))
                    continue
                if r.status_code == 400 and schema is not None and "json" in r.text.lower():
                    body.pop("response_format", None)  # server rejected JSON mode; rely on parsing
                    continue
                r.raise_for_status()
                data = r.json()
                usage = data.get("usage", {}) or {}
                return (data["choices"][0]["message"]["content"] or "",
                        usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"OpenAI-compatible call failed: {last_err}")

    # ---------------------------------------------------------- structured
    def json(self, messages: list[dict], model_cls: type[T], *, task: str,
             temperature: float = 0.0, max_tokens: int = 1024, retries: int = 2) -> T:
        """Return a validated pydantic object. Raises LLMError after retries."""
        schema = require_all(inline_refs(model_cls.model_json_schema()))
        shape = json.dumps(schema_shape(schema), ensure_ascii=False)
        msgs = [dict(m) for m in messages]
        msgs[-1]["content"] += (
            "\n\nRespond with ONLY a JSON object (no prose, no code fences) with exactly this shape:\n"
            + shape
        )
        last_err = ""
        for attempt in range(retries + 1):
            raw = self.chat(msgs, task=task, temperature=temperature, schema=schema,
                            max_tokens=max_tokens)
            try:
                data = extract_json(raw)
                if isinstance(data, list) and len(schema.get("properties", {})) == 1:
                    # model returned the bare list for a single-field wrapper
                    data = {next(iter(schema["properties"])): data}
                copied = find_placeholders(data)
                if copied:
                    raise PlaceholderCopied(
                        f"these fields contain the placeholder word instead of real content: {copied}. "
                        "Replace every placeholder with the actual value")
                return model_cls.model_validate(data)
            except (JSONExtractError, ValidationError, PlaceholderCopied) as e:
                last_err = str(e)[:600]
                msgs = msgs + [
                    {"role": "assistant", "content": raw[:2000]},
                    {"role": "user", "content": (
                        f"That output was invalid: {last_err}\n"
                        f"Reply again with ONLY valid JSON of this shape: {shape}")},
                ]
        raise LLMError(f"[{task}] could not get valid JSON after {retries + 1} attempts: {last_err}")

    # ---------------------------------------------------------- embeddings
    def embed(self, texts: list[str], embed_model: str) -> list[list[float]]:
        if self.settings.backend == "fake":
            raise LLMError("embeddings unavailable on fake backend")
        if self.settings.backend != "ollama":
            raise LLMError("embeddings are only wired for Ollama")
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            batch = texts[i : i + 32]
            t0 = time.time()
            r = requests.post(f"{self.settings.base_url}/api/embed",
                              json={"model": embed_model, "input": batch}, timeout=self.settings.timeout)
            r.raise_for_status()
            out.extend(r.json()["embeddings"])
            self.meter.record(task="embed", model=embed_model, prompt_tokens=sum(len(t) for t in batch) // 4,
                              completion_tokens=0, latency=time.time() - t0, cached=False)
        return out


def ping(settings: Settings) -> tuple[bool, str]:
    """Health check used by `forgeai doctor`."""
    if settings.backend == "fake":
        return True, "fake backend (tests only)"
    try:
        if settings.backend == "ollama":
            r = requests.get(f"{settings.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            missing = [m for m in {settings.model, settings.judge_model, settings.embed_model} if m and
                       not any(n == m or n.startswith(m + ":") or n.split(":")[0] == m for n in names)]
            if missing:
                return False, f"Ollama is up but these models are not pulled: {missing}. Run `ollama pull <name>`."
            return True, f"Ollama OK; models available: {names}"
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        r = requests.get(f"{settings.base_url.rstrip('/')}/models", headers=headers, timeout=10)
        r.raise_for_status()
        return True, "OpenAI-compatible endpoint OK"
    except requests.ConnectionError:
        hint = ("start the Ollama app (or run `ollama serve`)" if settings.backend == "ollama"
                else "check FORGE_BASE_URL and your network")
        return False, f"cannot connect to {settings.base_url} - {hint}"
    except Exception as e:  # noqa: BLE001
        return False, f"backend unreachable: {e}"


def default_responder(settings: Settings):
    """Responder for the fake backend (tests / plumbing smoke runs only)."""
    if settings.backend != "fake":
        return None
    from .testing.fake_llm import FakeResponder
    return FakeResponder()