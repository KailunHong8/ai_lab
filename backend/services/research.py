"""
Semantic retrieval over the investing principles library in investing_research/.

Primary path: chromadb + sentence-transformers (all-MiniLM-L6-v2, ~80MB, CPU-only).
  - Persistent index at <project_root>/chroma_principles/
  - Rebuilt automatically on first use or when REBUILD_INDEX=1 env var is set.
  - Adding a new book is as simple as dropping a file into investing_research/.

Fallback (keyword overlap): used automatically if chromadb/sentence-transformers
are not installed, or if the embedding call fails.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent.parent / "investing_research"
CHROMA_DIR = Path(__file__).parent.parent.parent / "chroma_principles"
CHUNK_SIZE = 400   # words per chunk — smaller = better semantic precision
CHUNK_OVERLAP = 50

# ── optional imports ───────────────────────────────────────────────────────────
try:
    import chromadb
    from chromadb.utils import embedding_functions
    _HAS_CHROMA = True
except ImportError:
    _HAS_CHROMA = False

try:
    from pypdf import PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False

# ── chunk builder (shared by both paths) ──────────────────────────────────────

def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        if not _HAS_PYPDF:
            return ""
        reader = PdfReader(str(path))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    return ""


def _build_chunks() -> list[dict]:
    chunks: list[dict] = []
    if not DOCS_DIR.exists():
        return chunks
    for path in DOCS_DIR.iterdir():
        raw = _extract_text(path)
        if not raw.strip():
            continue
        words = raw.split()
        step = CHUNK_SIZE - CHUNK_OVERLAP
        for i in range(0, max(1, len(words) - CHUNK_OVERLAP), step):
            window = words[i: i + CHUNK_SIZE]
            if len(window) < 20:
                continue
            chunks.append({
                "id": f"{path.stem}_{i}",
                "source": path.name,
                "text": " ".join(window),
            })
    return chunks


# ── chromadb semantic path ─────────────────────────────────────────────────────

_chroma_collection = None


def _get_collection():
    """Lazy-init or return cached chromadb collection."""
    global _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection

    if not _HAS_CHROMA:
        return None

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    collection = client.get_or_create_collection(
        name="investing_principles",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    # Build index if empty or explicitly requested
    if collection.count() == 0 or os.getenv("REBUILD_INDEX") == "1":
        _populate_collection(collection)

    _chroma_collection = collection
    return collection


def _populate_collection(collection) -> None:
    """Upsert all chunks into the collection."""
    chunks = _build_chunks()
    if not chunks:
        return

    # Process in batches of 100 to avoid memory spikes
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start: start + batch_size]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[{"source": c["source"]} for c in batch],
        )


def _semantic_search(query: str, top_k: int) -> list[dict]:
    """Query chromadb with cosine similarity. Returns top_k results."""
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    results = collection.query(
        query_texts=[query],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    out = []
    for i, doc in enumerate(results["documents"][0]):
        meta = results["metadatas"][0][i]
        dist = results["distances"][0][i]
        out.append({
            "source": meta.get("source", ""),
            "text": doc,
            "score": round(1.0 - dist, 4),  # cosine distance → similarity
        })
    return out


# ── keyword fallback ──────────────────────────────────────────────────────────

_kw_chunks: list[dict] | None = None


def _keyword_search(query: str, top_k: int) -> list[dict]:
    global _kw_chunks
    if _kw_chunks is None:
        _kw_chunks = _build_chunks()

    query_words = set(re.findall(r"\w+", query.lower()))
    if not query_words:
        return []

    scored = []
    for chunk in _kw_chunks:
        chunk_words = set(re.findall(r"\w+", chunk["text"].lower()))
        score = len(query_words & chunk_words)
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"source": c["source"], "text": c["text"], "score": s}
        for s, c in scored[:top_k]
    ]


# ── public API ─────────────────────────────────────────────────────────────────

def search_principles(query: str, top_k: int = 4) -> list[dict]:
    """
    Return top_k chunks most relevant to query.
    Uses chromadb semantic search when available, falls back to keyword overlap.
    """
    if _HAS_CHROMA:
        try:
            results = _semantic_search(query, top_k)
            if results:
                return results
        except Exception:
            pass
    return _keyword_search(query, top_k)


def rebuild_index() -> int:
    """Force a full re-index. Returns number of chunks indexed."""
    if not _HAS_CHROMA:
        return 0
    global _chroma_collection
    _chroma_collection = None

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name="investing_principles",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    try:
        client.delete_collection("investing_principles")
        collection = client.create_collection(
            name="investing_principles",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        pass

    chunks = _build_chunks()
    if chunks:
        _populate_collection(collection)
    _chroma_collection = collection
    return len(chunks)
