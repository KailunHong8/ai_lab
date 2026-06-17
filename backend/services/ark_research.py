"""
Semantic retrieval over ARK newsletter documents in ARK_newsletter/ (sibling of project root).

Separate Chroma collection "ark_newsletter" — never mixed with investing_principles.

Use cases:
  - Fuzzy recall: "where did ARK discuss exchange vertical integration?"
  - Citation snippets with source filename and date context
  - Exact questions are better served by the structured Thesis DB (search_theses)

The collection is rebuilt automatically when empty. Call rebuild_ark_index() to force.
Documents are sourced from ARK_DOCS_DIR (configurable via ARK_DOCS_DIR env var).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Default: sibling directory ../ARK_newsletter relative to project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent
ARK_DOCS_DIR = Path(os.getenv("ARK_DOCS_DIR", str(_PROJECT_ROOT.parent / "ARK_newsletter")))
ARK_CHROMA_DIR = _PROJECT_ROOT / "chroma_ark"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

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


def _extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        if not _HAS_PYPDF:
            return ""
        reader = PdfReader(str(path))
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    if path.suffix.lower() in (".txt", ".md"):
        return path.read_text(encoding="utf-8", errors="ignore")
    # Skip .mhtml and other binary formats
    return ""


def _build_ark_chunks() -> list[dict]:
    chunks: list[dict] = []
    if not ARK_DOCS_DIR.exists():
        return chunks
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for path in ARK_DOCS_DIR.iterdir():
        raw = _extract_text(path)
        if not raw.strip():
            continue
        words = raw.split()
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


_ark_collection = None


def _get_ark_collection():
    global _ark_collection
    if _ark_collection is not None:
        return _ark_collection

    if not _HAS_CHROMA:
        return None

    ARK_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(ARK_CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name="ark_newsletter",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() == 0 or os.getenv("REBUILD_ARK_INDEX") == "1":
        _populate_ark_collection(collection)

    _ark_collection = collection
    return collection


def _populate_ark_collection(collection) -> None:
    chunks = _build_ark_chunks()
    if not chunks:
        return
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start: start + batch_size]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[{"source": c["source"]} for c in batch],
        )


def _keyword_fallback(query: str, top_k: int) -> list[dict]:
    chunks = _build_ark_chunks()
    query_words = set(re.findall(r"\w+", query.lower()))
    if not query_words:
        return []
    scored = []
    for chunk in chunks:
        chunk_words = set(re.findall(r"\w+", chunk["text"].lower()))
        score = len(query_words & chunk_words)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"source": c["source"], "text": c["text"], "score": s}
        for s, c in scored[:top_k]
    ]


def search_ark(query: str, top_k: int = 4) -> list[dict]:
    """
    Return top_k ARK newsletter chunks most relevant to query.
    Uses chromadb semantic search when available, falls back to keyword overlap.
    """
    if _HAS_CHROMA:
        try:
            collection = _get_ark_collection()
            if collection and collection.count() > 0:
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
                        "score": round(1.0 - dist, 4),
                    })
                if out:
                    return out
        except Exception:
            pass
    return _keyword_fallback(query, top_k)


def add_document_to_ark(doc_id: str, source_name: str, content: str) -> int:
    """
    Incrementally index a new document into the ark_newsletter collection.
    Returns the number of chunks added.
    """
    if not _HAS_CHROMA:
        return 0
    collection = _get_ark_collection()
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


def remove_document_from_ark(doc_id: str) -> None:
    """Remove all chunks for a given doc_id prefix from the ark collection."""
    if not _HAS_CHROMA:
        return
    collection = _get_ark_collection()
    if collection is None:
        return
    try:
        # Chroma supports where-clause deletion; use id prefix pattern via get
        existing = collection.get(where={"source": {"$eq": doc_id}})
        ids_to_delete = existing.get("ids", [])
        if ids_to_delete:
            collection.delete(ids=ids_to_delete)
    except Exception:
        pass


def rebuild_ark_index() -> int:
    """Force a full re-index of ARK_DOCS_DIR. Returns number of chunks indexed."""
    if not _HAS_CHROMA:
        return 0
    global _ark_collection
    _ark_collection = None

    ARK_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(ARK_CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    try:
        client.delete_collection("ark_newsletter")
    except Exception:
        pass
    collection = client.create_collection(
        name="ark_newsletter",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    chunks = _build_ark_chunks()
    if chunks:
        _populate_ark_collection(collection)
    _ark_collection = collection
    return len(chunks)
