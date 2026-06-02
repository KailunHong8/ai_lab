"""
Knowledge base query layer.
- search_theses: query the structured thesis database
- get_entity_graph: return supplier/competitor/customer graph for a symbol
- full_text_search: keyword-overlap search over raw markdown documents
"""
import json
from pathlib import Path
from typing import Optional

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Thesis, Entity, EntityRelationship

DOCS_DIR = Path(__file__).parent.parent.parent / "knowledge_base" / "documents"


async def search_theses(
    entity: Optional[str],
    theme: Optional[str],
    limit: int,
    db: AsyncSession,
) -> list[dict]:
    q = select(Thesis)
    if entity:
        q = q.where(Thesis.entity == entity.upper())
    if theme:
        q = q.where(Thesis.theme.ilike(f"%{theme}%"))
    q = q.order_by(Thesis.date.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "entity": r.entity,
            "theme": r.theme,
            "stance": r.stance,
            "claims": json.loads(r.claims) if r.claims else [],
            "type": r.type,
            "date": r.date,
        }
        for r in rows
    ]


async def get_entity_graph(symbol: str, db: AsyncSession) -> dict:
    sym = symbol.upper()
    result = await db.execute(
        select(EntityRelationship).where(
            or_(
                EntityRelationship.from_symbol == sym,
                EntityRelationship.to_symbol == sym,
            )
        )
    )
    rels = result.scalars().all()

    graph: dict[str, list[dict]] = {}
    for r in rels:
        rel_type = r.relationship
        if rel_type not in graph:
            graph[rel_type] = []
        # From this symbol's perspective
        other = r.to_symbol if r.from_symbol == sym else r.from_symbol
        graph[rel_type].append({"symbol": other, "description": r.description or ""})

    return {"symbol": sym, "relationships": graph}


def _score_chunk(chunk: str, query_words: set[str]) -> int:
    words = set(chunk.lower().split())
    return len(words & query_words)


def full_text_search(query: str, limit: int = 4) -> list[dict]:
    """Keyword-overlap search over markdown files in knowledge_base/documents/."""
    if not DOCS_DIR.exists():
        return []

    query_words = set(query.lower().split())
    CHUNK_SIZE = 500
    OVERLAP = 50
    chunks: list[tuple[int, str, str]] = []  # (score, filename, text)

    for md_file in DOCS_DIR.glob("*.md"):
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        words = text.split()
        step = CHUNK_SIZE - OVERLAP
        for i in range(0, max(1, len(words) - 20), step):
            chunk = " ".join(words[i : i + CHUNK_SIZE])
            score = _score_chunk(chunk, query_words)
            if score > 0:
                chunks.append((score, md_file.name, chunk))

    chunks.sort(key=lambda x: x[0], reverse=True)
    return [
        {"source": fname, "text": text, "score": score}
        for score, fname, text in chunks[:limit]
    ]
