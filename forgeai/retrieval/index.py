"""BM25 retriever (no external services needed) with optional hybrid dense
search through Ollama embeddings, fused with Reciprocal Rank Fusion, and an
optional LLM query-expansion step."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from ..schemas import BaseModel

from ..schemas import RetrievalConfig
from ..textutil import tokens
from .chunker import Chunk, chunk_documents

__all__ = ["Retriever", "RetrievalConfig", "BM25"]


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [tokens(t) for t in texts]
        self.tf = [Counter(d) for d in self.docs]
        self.len = [len(d) for d in self.docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out


class _Expansion(BaseModel):
    keywords: list[str]


def coverage(query: str, text: str) -> float:
    q = set(tokens(query))
    if not q:
        return 0.0
    return len(q & set(tokens(text))) / len(q)


class Retriever:
    def __init__(self, docs, config: RetrievalConfig, llm=None, embed_model: str = "",
                 cache_dir: str = ".forge_cache"):
        self.config = config
        self.llm = llm
        self.embed_model = embed_model
        self.chunks: list[Chunk] = chunk_documents(docs, config.chunk_size, config.chunk_overlap,
                                                   config.prepend_headings)
        self.by_id = {c.chunk_id: c for c in self.chunks}
        self.bm25 = BM25([c.text for c in self.chunks])
        self.vectors: list[list[float]] | None = None
        self._cache_dir = Path(cache_dir)
        if config.mode == "hybrid" and llm is not None and embed_model:
            try:
                self.vectors = self._embed_cached([c.text for c in self.chunks])
            except Exception:  # embeddings unavailable -> degrade to BM25, recorded in .degraded
                self.vectors = None
        self.degraded = config.mode == "hybrid" and self.vectors is None

    # -------------------------------------------------------------- dense
    def _embed_cached(self, texts: list[str]) -> list[list[float]]:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256((self.embed_model + "\x00".join(texts)).encode()).hexdigest()[:24]
        f = self._cache_dir / f"emb_{key}.json"
        if f.exists():
            return json.loads(f.read_text())
        vecs = self.llm.embed(texts, self.embed_model)
        f.write_text(json.dumps(vecs))
        return vecs

    @staticmethod
    def _cos(a, b):
        num = sum(x * y for x, y in zip(a, b))
        den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
        return num / den if den else 0.0

    # ----------------------------------------------------------- expansion
    def expand(self, query: str) -> str:
        if not (self.config.query_expansion and self.llm is not None):
            return query
        try:
            res = self.llm.json(
                [{"role": "system", "content": "You rewrite search queries for a keyword search engine over company documents."},
                 {"role": "user", "content": (
                     "List 3 to 6 extra search keywords or synonyms (single words or short phrases) that the "
                     "document might use for this question. Do not answer the question.\n"
                     f"Question: {query}")}],
                _Expansion, task="query_expansion", max_tokens=120)
            return query + " " + " ".join(res.keywords[:6])
        except Exception:
            return query

    # --------------------------------------------------------------- search
    def search(self, query: str, top_k: int | None = None) -> list[tuple[Chunk, float]]:
        k = top_k or self.config.top_k
        q = self.expand(query)
        bm = self.bm25.scores(q)
        order_bm = sorted(range(len(bm)), key=lambda i: -bm[i])
        if self.vectors is not None:
            try:
                qv = self._embed_cached([q])[0]
                dense = [self._cos(qv, v) for v in self.vectors]
                order_dn = sorted(range(len(dense)), key=lambda i: -dense[i])
                rrf: dict[int, float] = {}
                for rank, i in enumerate(order_bm[:50]):
                    rrf[i] = rrf.get(i, 0) + 1 / (60 + rank)
                for rank, i in enumerate(order_dn[:50]):
                    rrf[i] = rrf.get(i, 0) + 1 / (60 + rank)
                order = sorted(rrf, key=lambda i: -rrf[i])
                scored = [(self.chunks[i], rrf[i]) for i in order[:k]]
            except Exception:
                scored = [(self.chunks[i], bm[i]) for i in order_bm[:k] if bm[i] > 0]
        else:
            scored = [(self.chunks[i], bm[i]) for i in order_bm[:k] if bm[i] > 0]
        if self.config.min_relevance > 0:
            scored = [(c, s) for c, s in scored if coverage(query, c.text) >= self.config.min_relevance]
        return scored

    def rank_of(self, query: str, predicate, depth: int = 50) -> int | None:
        """1-based rank of the first chunk satisfying predicate (diagnostics)."""
        for r, (c, _) in enumerate(self.search(query, top_k=depth), start=1):
            if predicate(c):
                return r
        return None
