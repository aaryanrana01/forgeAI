"""Load a folder of documents (PDF, TXT, MD, CSV, DOCX, JSON) into plain text
plus structure, and build an inventory the intake interviewer can read."""

from __future__ import annotations

import csv
import io
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..textutil import tokens

SUPPORTED = {".pdf", ".txt", ".md", ".markdown", ".csv", ".docx", ".json"}


@dataclass
class Document:
    doc_id: str            # file name, used in citations
    path: str
    kind: str              # pdf | text | csv | docx | json
    text: str
    pages: list[str] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)   # csv only
    rows: list[dict] = field(default_factory=list)     # csv only

    @property
    def n_words(self) -> int:
        return len(self.text.split())


_HEADING = re.compile(
    r"^(?:(?:section|part|chapter)\s+\d+[.:]?\s+.+|\d+(?:\.\d+)*[.)]?\s+[A-Z].{2,80}|[A-Z][A-Z &/\-]{3,70})$"
)


def _headings(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if 3 < len(s) < 90 and not s.endswith((".", ",", ";")) and (
            _HEADING.match(s) or line.lstrip().startswith("#")
        ):
            out.append(s)
    return out


def _read_pdf(path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for p in reader.pages:
        t = p.extract_text() or ""
        t = re.sub(r"[ \t]+", " ", t)
        pages.append(t.strip())
    return pages


def _read_docx(path: Path) -> str:
    try:
        import docx  # python-docx
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install python-docx to read .docx files") from e
    d = docx.Document(str(path))
    lines = []
    for para in d.paragraphs:
        if para.style.name.lower().startswith("heading"):
            lines.append("# " + para.text)
        else:
            lines.append(para.text)
    return "\n".join(lines)


def load_file(path: Path) -> Document | None:
    ext = path.suffix.lower()
    if ext not in SUPPORTED:
        return None
    if ext == ".pdf":
        pages = _read_pdf(path)
        text = "\n\n".join(pages)
        return Document(path.name, str(path), "pdf", text, pages=pages, headings=_headings(text))
    if ext in (".txt", ".md", ".markdown"):
        text = path.read_text(errors="ignore")
        return Document(path.name, str(path), "text", text, pages=[text], headings=_headings(text))
    if ext == ".docx":
        text = _read_docx(path)
        return Document(path.name, str(path), "docx", text, pages=[text], headings=_headings(text))
    if ext == ".json":
        raw = path.read_text(errors="ignore")
        try:
            text = json.dumps(json.loads(raw), indent=1, ensure_ascii=False)
        except json.JSONDecodeError:
            text = raw
        return Document(path.name, str(path), "json", text, pages=[text])
    if ext == ".csv":
        raw = path.read_text(errors="ignore")
        reader = csv.DictReader(io.StringIO(raw))
        rows = [{k.strip(): (v or "").strip() for k, v in r.items() if k} for r in reader]
        cols = [c.strip() for c in (reader.fieldnames or [])]
        text = "\n".join(" | ".join(f"{k}: {v}" for k, v in r.items()) for r in rows)
        return Document(path.name, str(path), "csv", text, pages=[text], columns=cols, rows=rows)
    return None


def load_folder(folder: str | Path) -> list[Document]:
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"documents folder not found: {folder}")
    docs = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not p.name.startswith("."):
            d = load_file(p)
            if d and d.text.strip():
                docs.append(d)
    if not docs:
        raise ValueError(f"no readable documents in {folder} (supported: {sorted(SUPPORTED)})")
    return docs


def inventory(docs: list[Document], *, max_headings: int = 25) -> dict:
    """Compact, model-readable description of the document folder."""
    items = []
    for d in docs:
        entry: dict = {"doc_id": d.doc_id, "type": d.kind, "words": d.n_words}
        if d.kind == "csv":
            entry["columns"] = d.columns
            entry["n_rows"] = len(d.rows)
            entry["sample_rows"] = d.rows[:3]
        else:
            entry["pages"] = len(d.pages)
            entry["headings"] = d.headings[:max_headings]
            kw = Counter(t for t in tokens(d.text) if len(t) > 3 and not t.isdigit())
            entry["top_terms"] = [w for w, _ in kw.most_common(15)]
            entry["opening"] = " ".join(d.text.split()[:60])
        items.append(entry)
    return {"n_documents": len(docs), "documents": items}


def inventory_text(inv: dict) -> str:
    lines = [f"{inv['n_documents']} document(s):"]
    for d in inv["documents"]:
        if d["type"] == "csv":
            lines.append(f"- {d['doc_id']} (CSV table, {d['n_rows']} rows) columns: {', '.join(d['columns'])}")
            for r in d["sample_rows"][:2]:
                lines.append(f"    sample row: {json.dumps(r, ensure_ascii=False)[:300]}")
        else:
            lines.append(f"- {d['doc_id']} ({d['type']}, {d['pages']} page(s), {d['words']} words)")
            if d.get("headings"):
                lines.append(f"    sections: {'; '.join(d['headings'][:20])}")
            lines.append(f"    key terms: {', '.join(d.get('top_terms', []))}")
    return "\n".join(lines)


_GENERIC_COLS = {"usd", "inr", "day", "qty", "no", "id", "name", "code", "type"}


def table_match(text: str, docs: list[Document]) -> tuple[str, list[str]]:
    """Does `text` (a topic or question) ask about a CSV table's columns? Returns (doc_id, matched words)
    when at least two column words match, or the table's name plus one column word."""
    want = set(tokens(text))
    best: tuple[str, list[str]] = ("", [])
    for d in docs:
        if d.kind != "csv":
            continue
        cols = set()
        for c in d.columns:
            cols |= {t for t in tokens(c.replace("_", " ")) if len(t) > 2 and t not in _GENERIC_COLS}
        stem = {t for t in tokens(d.doc_id.rsplit(".", 1)[0].replace("_", " ")) if len(t) > 3}
        col_hit, stem_hit = cols & want, stem & want
        hit = sorted(col_hit | stem_hit)
        if (len(col_hit) >= 2 or (stem_hit and col_hit)) and len(hit) > len(best[1]):
            best = (d.doc_id, hit)
    return best
