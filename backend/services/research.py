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


# ── incremental index helpers ─────────────────────────────────────────────────

def add_document_to_principles(doc_id: str, source_name: str, content: str) -> int:
    """Incrementally upsert chunks for a single document. Returns chunk count."""
    if not _HAS_CHROMA:
        return 0
    collection = _get_collection()
    if collection is None:
        return 0
    words = content.split()
    step = CHUNK_SIZE - CHUNK_OVERLAP
    chunks = []
    for i in range(0, max(1, len(words) - CHUNK_OVERLAP), step):
        window = words[i: i + CHUNK_SIZE]
        if len(window) < 20:
            continue
        chunks.append({
            "id": f"{doc_id}_{i}",
            "source": source_name,
            "text": " ".join(window),
        })
    if not chunks:
        return 0
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start: start + batch_size]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[{"source": c["source"]} for c in batch],
        )
    return len(chunks)


def remove_document_from_principles(doc_id: str) -> None:
    """Remove all chunks for a given doc_id prefix from the principles collection."""
    if not _HAS_CHROMA:
        return
    collection = _get_collection()
    if collection is None:
        return
    try:
        existing = collection.get(where={"source": {"$eq": doc_id}})
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
    except Exception:
        pass


# ── hybrid fusion (Reciprocal Rank Fusion) ─────────────────────────────────────

RRF_K = 60          # standard RRF constant (Cormack et al. 2009); rarely needs tuning
CANDIDATE_K = 25    # over-fetch this many per retriever before fusing


def _rrf_fuse(ranked_lists: list[list[dict]], k: int = RRF_K) -> list[dict]:
    """
    Reciprocal Rank Fusion: combine ranked result lists using rank position only,
    so incompatible score scales (cosine similarity vs keyword overlap) never mix.
    score(d) = Σ 1 / (k + rank_i(d)) across the lists d appears in.
    """
    scores: dict[tuple, float] = {}
    items: dict[tuple, dict] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            key = (item["source"], item["text"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            items.setdefault(key, item)
    fused = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    out = []
    for key, score in fused:
        merged = dict(items[key])
        merged["score"] = round(score, 6)   # RRF fusion score, not raw similarity
        out.append(merged)
    return out


# ── public API ─────────────────────────────────────────────────────────────────

def search_principles(query: str, top_k: int = 8) -> list[dict]:
    """
    Return top_k chunks most relevant to query.

    Hybrid retrieval: over-fetch candidates from both the semantic (chromadb) and
    keyword paths, fuse them with Reciprocal Rank Fusion, then trim to top_k.
    Dense recovers paraphrase/synonymy; keyword recovers exact terms, tickers, and
    proper nouns the embedding misses. Falls back to whichever path is available.
    """
    dense: list[dict] = []
    if _HAS_CHROMA:
        try:
            dense = _semantic_search(query, CANDIDATE_K)
        except Exception:
            dense = []

    keyword = _keyword_search(query, CANDIDATE_K)

    if dense and keyword:
        return _rrf_fuse([dense, keyword])[:top_k]
    return (dense or keyword)[:top_k]


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
