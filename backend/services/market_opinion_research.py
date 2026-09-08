"""
Semantic retrieval over the market-opinion corpus (fund letters, Perplexity web research).

Single shared Chroma collection "market_opinion" — ARK, GMO, Sequoia, Bridgewater,
and Perplexity web research all land here.  Sources are differentiated via metadata
filters (fund, source_type), not per-source collections (spec §8 vector collection decision).

Replaces the ARK-specific ark_research.py collection for new ingestion.
Existing chroma_ark/ data is NOT migrated automatically — run /api/knowledge/reindex-market
to rebuild from the DB if needed.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

# Sentinel epoch for evergreen (no expiry) documents: year 2286
_EPOCH_EVERGREEN = 9999999999

_PROJECT_ROOT = Path(__file__).parent.parent.parent
MARKET_CHROMA_DIR = _PROJECT_ROOT / "chroma_market_opinion"
CHUNK_SIZE = 400
CHUNK_OVERLAP = 50

try:
    import chromadb
    from chromadb.utils import embedding_functions
    _HAS_CHROMA = True
except ImportError:
    _HAS_CHROMA = False


# ── collection ─────────────────────────────────────────────────────────────────

_market_collection = None


def _get_collection():
    global _market_collection
    if _market_collection is not None:
        return _market_collection
    if not _HAS_CHROMA:
        return None
    MARKET_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(MARKET_CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    collection = client.get_or_create_collection(
        name="market_opinion",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    _market_collection = collection
    return collection


# ── incremental index helpers ──────────────────────────────────────────────────

def expiration_epoch(expiration_at: datetime | None) -> int:
    """Return an integer epoch for Chroma metadata freshness filtering.
    None / no-expiry → evergreen sentinel 9999999999.
    """
    if expiration_at is None:
        return _EPOCH_EVERGREEN
    return int(expiration_at.timestamp())


def add_document(doc_id: str, content: str, metadata: dict | None = None) -> int:
    """
    Upsert chunks for one document into the market_opinion collection.
    metadata keys: source_type, fund, channel, recency_flag, reliability_tier,
    expiration_epoch (derived from expiration_at if present).
    Returns chunk count.
    """
    if not _HAS_CHROMA:
        return 0
    collection = _get_collection()
    if collection is None:
        return 0
    meta_base = {k: str(v) for k, v in (metadata or {}).items() if v is not None and k != "expiration_at"}
    meta_base["doc_id"] = doc_id
    # Store expiration as numeric epoch so Chroma $gt filter works
    if "expiration_epoch" not in meta_base:
        exp_at = (metadata or {}).get("expiration_at")
        if isinstance(exp_at, datetime):
            meta_base["expiration_epoch"] = str(int(exp_at.timestamp()))
        elif exp_at is not None:
            meta_base["expiration_epoch"] = str(exp_at)
        else:
            meta_base["expiration_epoch"] = str(_EPOCH_EVERGREEN)

    words = content.split()
    step = CHUNK_SIZE - CHUNK_OVERLAP
    chunks = []
    for i in range(0, max(1, len(words) - CHUNK_OVERLAP), step):
        window = words[i: i + CHUNK_SIZE]
        if len(window) < 20:
            continue
        chunks.append({
            "id": f"{doc_id}_{i}",
            "text": " ".join(window),
            "meta": {**meta_base, "chunk_index": str(i)},
        })
    if not chunks:
        return 0
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start: start + batch_size]
        collection.upsert(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            metadatas=[c["meta"] for c in batch],
        )
    return len(chunks)


def remove_document(doc_id: str) -> None:
    """Remove all chunks for doc_id from the market_opinion collection."""
    if not _HAS_CHROMA:
        return
    collection = _get_collection()
    if collection is None:
        return
    try:
        existing = collection.get(where={"doc_id": {"$eq": doc_id}})
        ids = existing.get("ids", [])
        if ids:
            collection.delete(ids=ids)
    except Exception:
        pass


# ── search ─────────────────────────────────────────────────────────────────────

def _keyword_search(query: str, top_k: int, where: dict | None = None, exclude_stale: bool = True) -> list[dict]:
    """Keyword fallback with optional freshness filtering."""
    if not _HAS_CHROMA:
        return []
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []
    try:
        results = collection.get(include=["documents", "metadatas"])
    except Exception:
        return []
    now_epoch = int(time.time())
    query_words = set(re.findall(r"\w+", query.lower()))
    scored = []
    for doc, meta in zip(results.get("documents", []), results.get("metadatas", [])):
        if where:
            match = all(meta.get(k) == v for k, v in where.items())
            if not match:
                continue
        if exclude_stale:
            try:
                if int(meta.get("expiration_epoch", _EPOCH_EVERGREEN)) <= now_epoch:
                    continue
            except (ValueError, TypeError):
                pass
        score = len(query_words & set(re.findall(r"\w+", doc.lower())))
        if score > 0:
            scored.append((score, doc, meta))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {"source": m.get("fund") or m.get("source_type", ""), "text": d, "score": s, "metadata": m}
        for s, d, m in scored[:top_k]
    ]


def search_market_opinion(
    query: str,
    top_k: int = 8,
    fund: str | None = None,
    source_type: str | None = None,
    exclude_stale: bool = True,
) -> list[dict]:
    """
    Semantic search over the market_opinion collection.
    Optionally filter by fund (e.g. "ARK") or source_type (e.g. "web_research").
    exclude_stale=True (default) omits documents whose expiration_epoch has passed.
    Falls back to keyword search when Chroma unavailable or empty.
    """
    if not _HAS_CHROMA:
        return []
    collection = _get_collection()
    if collection is None or collection.count() == 0:
        return []

    filters: dict = {}
    if fund:
        filters["fund"] = fund
    if source_type:
        filters["source_type"] = source_type
    if exclude_stale:
        filters["expiration_epoch"] = {"$gt": int(time.time())}

    # Build Chroma where clause
    where: dict | None = None
    # Separate equality filters from range filters
    eq_filters = {k: v for k, v in filters.items() if isinstance(v, str)}
    range_filters = {k: v for k, v in filters.items() if isinstance(v, dict)}

    all_clauses = []
    for k, v in eq_filters.items():
        all_clauses.append({k: {"$eq": v}})
    for k, v in range_filters.items():
        all_clauses.append({k: v})

    if len(all_clauses) == 1:
        where = all_clauses[0]
    elif len(all_clauses) > 1:
        where = {"$and": all_clauses}

    try:
        kwargs: dict = {
            "query_texts": [query],
            "n_results": min(top_k, collection.count()),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        results = collection.query(**kwargs)
        out = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            out.append({
                "source": meta.get("fund") or meta.get("source_type", ""),
                "text": doc,
                "score": round(1.0 - dist, 4),
                "metadata": meta,
            })
        return out
    except Exception:
        return _keyword_search(query, top_k, eq_filters or None, exclude_stale=exclude_stale)


# ── rebuild from DB ────────────────────────────────────────────────────────────

async def rebuild_market_opinion_index() -> int:
    """
    Full re-index: load all market_opinion documents from DB and upsert into Chroma.
    Returns total chunk count.
    """
    if not _HAS_CHROMA:
        return 0
    global _market_collection
    _market_collection = None

    MARKET_CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(MARKET_CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    try:
        client.delete_collection("market_opinion")
    except Exception:
        pass
    collection = client.create_collection(
        name="market_opinion",
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
    _market_collection = collection

    from backend.db import SessionLocal
    from backend.models import Document, CORPUS_MARKET_OPINION
    from sqlalchemy import select

    total = 0
    async with SessionLocal() as db:
        result = await db.execute(
            select(Document).where(Document.corpus == CORPUS_MARKET_OPINION)
        )
        docs = result.scalars().all()
        for doc in docs:
            meta = {
                "source_type": doc.source_type or "",
                "fund": doc.fund or "",
                "channel": doc.channel or "",
                "recency_flag": doc.recency_flag or "",
                "reliability_tier": str(doc.reliability_tier or ""),
                "expiration_epoch": str(expiration_epoch(doc.expiration_at)),
            }
            total += add_document(doc.id, doc.content, meta)
    return total
