import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Document
from backend.services import knowledge_base

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/upload")
async def upload_document(
    title: str = Form(...),
    source: str = Form("ARK"),
    date: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Add a document to the knowledge base by file upload or pasted text."""
    if file:
        raw = await file.read()
        filename = (file.filename or "").lower()
        is_pdf  = filename.endswith(".pdf") or file.content_type == "application/pdf"
        is_mbox = filename.endswith(".mbox")

        if is_mbox:
            from backend.services.mbox_parser import parse_mbox
            try:
                emails = parse_mbox(raw)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Could not parse .mbox: {exc}")
            if not emails:
                raise HTTPException(status_code=400, detail="No emails found in .mbox file.")

            imported = 0
            duplicates = 0
            new_doc_ids: list[str] = []

            from backend.services.knowledge_base import DOCS_DIR
            DOCS_DIR.mkdir(parents=True, exist_ok=True)

            for em in emails:
                content = em["content"]
                if not content.strip():
                    continue
                doc_id = hashlib.sha256(content.encode()).hexdigest()[:32]
                existing = await db.execute(select(Document).where(Document.id == doc_id))
                if existing.scalar_one_or_none():
                    duplicates += 1
                    continue

                safe_date = (em["date"] or "unknown").replace("-", "")
                (DOCS_DIR / f"{safe_date}_{doc_id[:8]}.md").write_text(content, encoding="utf-8")

                doc = Document(
                    id=doc_id,
                    source=source,
                    title=em["subject"] or title,
                    content=content,
                    date=em["date"] or None,
                    processed=False,
                )
                db.add(doc)
                new_doc_ids.append((doc_id, content))
                imported += 1

            await db.commit()

            # Run thesis extraction in the background — don't block the HTTP response.
            # Documents show as "Pending" in the UI until extraction completes.
            if new_doc_ids:
                import asyncio
                from backend.services import thesis_extractor
                from backend.db import SessionLocal

                async def _extract_all():
                    for did, content in new_doc_ids:
                        try:
                            async with SessionLocal() as bg_db:
                                await thesis_extractor.extract_and_save(did, content, bg_db)
                        except Exception:
                            pass  # log if needed, but don't crash the background task

                asyncio.create_task(_extract_all())

            return {"status": "ok", "imported": imported, "duplicates": duplicates}

        elif is_pdf:
            try:
                from pypdf import PdfReader
                import io
                reader = PdfReader(io.BytesIO(raw))
                content = "\n".join(
                    page.extract_text() or "" for page in reader.pages
                )
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Could not parse PDF: {exc}")
        else:
            content = raw.decode("utf-8", errors="replace")
    elif text:
        content = text
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or text.")

    if not content.strip():
        raise HTTPException(status_code=400, detail="Document content is empty.")

    doc_id = hashlib.sha256(content.encode()).hexdigest()[:32]

    existing = await db.execute(select(Document).where(Document.id == doc_id))
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "id": doc_id}

    from backend.services.knowledge_base import DOCS_DIR
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    safe_date = (date or "unknown").replace("-", "")
    (DOCS_DIR / f"{safe_date}_{doc_id[:8]}.md").write_text(content, encoding="utf-8")

    doc = Document(
        id=doc_id,
        source=source,
        title=title,
        content=content,
        date=date or None,
        processed=False,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from backend.services import thesis_extractor
    await thesis_extractor.extract_and_save(doc_id, content, db)

    return {"status": "ok", "id": doc_id, "title": title}


@router.get("/documents")
async def list_documents(
    source: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List documents in the knowledge base."""
    q = select(Document)
    if source:
        q = q.where(Document.source == source)
    q = q.order_by(Document.created_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {"id": r.id, "title": r.title, "source": r.source, "date": r.date, "processed": r.processed}
        for r in rows
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a document and its extracted theses."""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}


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
