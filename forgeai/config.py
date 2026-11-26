"""Runtime settings. Everything can be overridden with environment variables
(or a .env file in the project root) so the same code runs on a laptop with
Ollama, on a free hosted open-model API, or in tests with a fake model."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Tiny .env loader (avoids an extra dependency)."""
    for candidate in (Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            break


_load_dotenv()


@dataclass
class Settings:
    # "ollama" (local open model, default) | "openai" (any OpenAI-compatible
    # server serving an open model: Groq, vLLM, LM Studio, llama.cpp server) | "fake" (tests)
    backend: str = field(default_factory=lambda: os.getenv("FORGE_BACKEND", "ollama"))
    model: str = field(default_factory=lambda: os.getenv("FORGE_MODEL", "qwen2.5:7b-instruct"))
    # A different model family for judging reduces self-preference bias.
    # Falls back to `model` when not set.
    judge_model: str = field(default_factory=lambda: os.getenv("FORGE_JUDGE_MODEL", ""))
    # Optional embedding model for hybrid retrieval (Ollama only). Empty = BM25 only.
    embed_model: str = field(default_factory=lambda: os.getenv("FORGE_EMBED_MODEL", ""))
    base_url: str = field(default_factory=lambda: os.getenv("FORGE_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.getenv("FORGE_API_KEY", ""))
    timeout: int = field(default_factory=lambda: int(os.getenv("FORGE_TIMEOUT", "300")))
    num_ctx: int = field(default_factory=lambda: int(os.getenv("FORGE_NUM_CTX", "8192")))
    seed: int = field(default_factory=lambda: int(os.getenv("FORGE_SEED", "7")))
    use_cache: bool = field(default_factory=lambda: os.getenv("FORGE_CACHE", "1") == "1")
    cache_dir: str = field(default_factory=lambda: os.getenv("FORGE_CACHE_DIR", ".forge_cache"))

    def __post_init__(self) -> None:
        if not self.base_url:
            self.base_url = "http://localhost:11434" if self.backend == "ollama" else "https://api.groq.com/openai/v1"
        if not self.judge_model:
            self.judge_model = self.model

    def describe(self) -> dict:
        return {
            "backend": self.backend,
            "model": self.model if self.backend != "fake" else "fake-scripted-test-model",
            "judge_model": self.judge_model if self.backend != "fake" else "fake-scripted-test-model",
            "embed_model": self.embed_model or None,
            "base_url": self.base_url if self.backend != "fake" else None,
            "seed": self.seed,
        }


@dataclass
class Budget:
    """Per-run budget. The optimizer loop stops early when it is spent or when
    an iteration stops paying for itself."""

    max_tokens: int = field(default_factory=lambda: int(os.getenv("FORGE_MAX_TOKENS", "4000000")))
    max_seconds: int = field(default_factory=lambda: int(os.getenv("FORGE_MAX_SECONDS", "14400")))
    max_llm_calls: int = field(default_factory=lambda: int(os.getenv("FORGE_MAX_CALLS", "3000")))
    # An iteration must improve the dev pass-rate by at least this many
    # percentage points per 100k tokens spent, otherwise we stop iterating.
    min_gain_pp_per_100k_tokens: float = field(
        default_factory=lambda: float(os.getenv("FORGE_MIN_GAIN", "0.5"))
    )
