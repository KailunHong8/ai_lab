import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.services import knowledge_base

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/ingest")
async def ingest(db: AsyncSession = Depends(get_db)):
    """Sync emails from the configured Gmail label and extract theses."""
    from backend.services import gmail_ingestion

    label = os.getenv("GMAIL_LABEL", "Research/ARK")
    try:
        count = await gmail_ingestion.sync_gmail(label, db)
        return {"ingested": count, "label": label}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {exc}")


@router.get("/theses")
async def get_theses(
    entity: Optional[str] = None,
    theme: Optional[str] = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Query the structured thesis database by entity (ticker) or theme."""
    return await knowledge_base.search_theses(entity, theme, limit, db)


@router.get("/entity/{symbol}")
async def get_entity(symbol: str, db: AsyncSession = Depends(get_db)):
    """Get the entity graph (suppliers, competitors, customers) for a ticker."""
    return await knowledge_base.get_entity_graph(symbol, db)


@router.get("/search")
async def search_docs(q: str, limit: int = 4):
    """Full-text keyword search over raw markdown documents."""
    return knowledge_base.full_text_search(q, limit)
