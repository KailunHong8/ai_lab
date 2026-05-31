"""
Keyword-based retrieval over the research corpus in docs/.
Chunks text files (context.txt) and extracted PDF text into ~500-word windows,
then returns the top-k chunks whose words overlap most with the query.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# pypdf is optional – we gracefully skip PDFs if it's not installed
try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False

DOCS_DIR = Path(__file__).parent.parent.parent / "investing_research"
CHUNK_SIZE = 500   # words per chunk
CHUNK_OVERLAP = 50  # words of overlap between consecutive chunks

_chunks: list[dict] | None = None  # lazy-loaded cache


def _extract_text_from_pdf(path: Path) -> str:
    if not _HAS_PYPDF:
        return ""
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)
    return "\n".join(parts)


def _extract_text_from_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _build_chunks() -> list[dict]:
    chunks: list[dict] = []
    for path in DOCS_DIR.iterdir():
        if path.suffix.lower() == ".pdf":
            raw = _extract_text_from_pdf(path)
        elif path.suffix.lower() in (".txt", ".md"):
            raw = _extract_text_from_txt(path)
        else:
            continue

        words = raw.split()
        step = CHUNK_SIZE - CHUNK_OVERLAP
        for i in range(0, max(1, len(words) - CHUNK_OVERLAP), step):
            window = words[i : i + CHUNK_SIZE]
            if len(window) < 20:
                continue
            chunks.append({"source": path.name, "text": " ".join(window)})
    return chunks


def _get_chunks() -> list[dict]:
    global _chunks
    if _chunks is None:
        _chunks = _build_chunks()
    return _chunks


def search_research(query: str, top_k: int = 4) -> list[dict]:
    """Return top_k chunks most relevant to query (keyword overlap)."""
    query_words = set(re.findall(r"\w+", query.lower()))
    if not query_words:
        return []

    scored: list[tuple[int, dict]] = []
    for chunk in _get_chunks():
        chunk_words = set(re.findall(r"\w+", chunk["text"].lower()))
        score = len(query_words & chunk_words)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]
