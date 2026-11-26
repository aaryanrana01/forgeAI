"""Paragraph-aware chunking with optional section-heading prefixes.

Chunk ids are stable and human readable: "<doc_id>#<n>". CSV files are chunked
by rows so a table row can be retrieved and cited like any passage."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..docs.loader import Document, _HEADING


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    text: str          # what the model sees
    section: str = ""
    page: int = 0

    def render(self) -> str:
        return f"[{self.chunk_id}] {self.text}"


def _paragraphs(page_text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", page_text) if p.strip()]
    if len(paras) <= 1:  # PDFs often lose blank lines; fall back to line groups
        lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        paras, cur = [], []
        for ln in lines:
            is_head = bool(_HEADING.match(ln)) and len(ln) < 90
            if is_head:
                if cur:
                    paras.append(" ".join(cur))
                    cur = []
                paras.append(ln)
                continue
            cur.append(ln)
            if ln.endswith((".", ":")) and len(" ".join(cur).split()) > 60:
                paras.append(" ".join(cur))
                cur = []
        if cur:
            paras.append(" ".join(cur))
    return paras


def _is_heading(p: str) -> bool:
    return len(p) < 90 and bool(_HEADING.match(p.strip().lstrip("#").strip()))


def chunk_document(doc: Document, chunk_size: int = 180, overlap: int = 40,
                   prepend_headings: bool = True, csv_rows_per_chunk: int = 1) -> list[Chunk]:
    chunks: list[Chunk] = []
    if doc.kind == "csv":
        for i in range(0, len(doc.rows), csv_rows_per_chunk):
            rows = doc.rows[i : i + csv_rows_per_chunk]
            text = "\n".join(" | ".join(f"{k}: {v}" for k, v in r.items()) for r in rows)
            chunks.append(Chunk(f"{doc.doc_id}#{i // csv_rows_per_chunk}", doc.doc_id,
                                f"(row from {doc.doc_id}) {text}", section="table"))
        return chunks

    section = ""
    buf: list[str] = []          # words of the chunk being built
    buf_section, buf_page = "", 0
    fresh = 0                    # words in buf that are not overlap carry-over
    n = 0

    def emit(carry: bool) -> None:
        nonlocal buf, n, fresh
        if fresh == 0:
            buf = []
            return
        if prepend_headings:
            prefix = f"({doc.doc_id} > {buf_section}) " if buf_section else f"({doc.doc_id}) "
        else:
            prefix = ""
        chunks.append(Chunk(f"{doc.doc_id}#{n}", doc.doc_id, prefix + " ".join(buf),
                            section=buf_section, page=buf_page))
        n += 1
        buf = buf[-overlap:] if (carry and overlap) else []
        fresh = 0

    for page_no, page in enumerate(doc.pages or [doc.text], start=1):
        for para in _paragraphs(page):
            if _is_heading(para):
                # a new section starts a new chunk unless the current one is still small
                if fresh >= chunk_size * 0.5:
                    emit(carry=False)
                section = para.strip().lstrip("#").strip()
                if fresh == 0:
                    buf_section, buf_page = section, page_no
                buf.extend(section.split())   # keep the heading words searchable
                fresh += len(section.split())
                continue
            words = para.split()
            if fresh == 0:
                buf_section, buf_page = section, page_no
            # keep paragraphs whole when they fit; otherwise close the chunk first
            if fresh and len(buf) + len(words) > chunk_size:
                emit(carry=True)
                buf_section, buf_page = section, page_no
            while len(buf) + len(words) > chunk_size:   # paragraph longer than a chunk
                room = max(1, chunk_size - len(buf))
                buf.extend(words[:room])
                fresh += min(room, len(words))
                words = words[room:]
                emit(carry=True)
                buf_section, buf_page = section, page_no
            buf.extend(words)
            fresh += len(words)
    emit(carry=False)
    return chunks


def chunk_documents(docs: list[Document], chunk_size: int = 180, overlap: int = 40,
                    prepend_headings: bool = True) -> list[Chunk]:
    out: list[Chunk] = []
    for d in docs:
        out.extend(chunk_document(d, chunk_size, overlap, prepend_headings))
    return out
