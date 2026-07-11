import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import (
    Document,
    CORPUS_PRINCIPLES, CORPUS_MARKET_OPINION,
    SOURCE_TYPE_PRINCIPLE_TEXT, SOURCE_TYPE_FUND_LETTER, SOURCE_TYPE_WEB_RESEARCH,
    CHANNEL_MANUAL_PASTE, CHANNEL_FILE_UPLOAD, CHANNEL_MBOX, CHANNEL_PERPLEXITY,
    RECENCY_EVERGREEN, RECENCY_TIMELY,
    RELIABILITY_PRINCIPLES, RELIABILITY_FUND_LETTER, RELIABILITY_WEB_RESEARCH,
)
from backend.services import knowledge_base

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

_FUND_NAMES = {"ARK", "GMO", "SEQUOIA", "BRIDGEWATER"}

TTL_DAYS_WEB_RESEARCH = 30


def _classify_corpus(source: str) -> tuple[str, str, int]:
    """Return (corpus, source_type, reliability_tier) based on source label."""
    if source.upper() in _FUND_NAMES:
        return CORPUS_MARKET_OPINION, SOURCE_TYPE_FUND_LETTER, RELIABILITY_FUND_LETTER
    return CORPUS_PRINCIPLES, SOURCE_TYPE_PRINCIPLE_TEXT, RELIABILITY_PRINCIPLES


def _index_document(doc: Document, content: str) -> None:
    """Dispatch document to the correct Chroma collection based on corpus."""
    import asyncio
    if doc.corpus == CORPUS_MARKET_OPINION:
        from backend.services.market_opinion_research import add_document as add_market
        meta = {
            "source_type": doc.source_type or "",
            "fund": doc.fund or "",
            "channel": doc.channel or "",
            "recency_flag": doc.recency_flag or "",
            "reliability_tier": str(doc.reliability_tier or ""),
        }
        asyncio.get_event_loop().run_in_executor(None, add_market, doc.id, content, meta)
    else:
        from backend.services.research import add_document_to_principles
        asyncio.get_event_loop().run_in_executor(None, add_document_to_principles, doc.id, doc.id, content)


async def _async_index_document(doc: Document, content: str) -> None:
    import asyncio
    if doc.corpus == CORPUS_MARKET_OPINION:
        from backend.services.market_opinion_research import add_document as add_market
        meta = {
            "source_type": doc.source_type or "",
            "fund": doc.fund or "",
            "channel": doc.channel or "",
            "recency_flag": doc.recency_flag or "",
            "reliability_tier": str(doc.reliability_tier or ""),
        }
        await asyncio.to_thread(add_market, doc.id, content, meta)
    else:
        from backend.services.research import add_document_to_principles
        await asyncio.to_thread(add_document_to_principles, doc.id, doc.id, content)


@router.post("/upload")
async def upload_document(
    title: str = Form(...),
    source: str = Form("manual"),
    date: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    text: Optional[str] = Form(None),
    provider: str = Form("bedrock"),
    model: Optional[str] = Form(None),
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

            corpus, source_type, reliability_tier = _classify_corpus(source)
            recency_flag = RECENCY_EVERGREEN if corpus == CORPUS_PRINCIPLES else RECENCY_TIMELY

            imported = 0
            duplicates = 0
            new_doc_ids: list[tuple[str, str]] = []

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
                    corpus=corpus,
                    source_type=source_type,
                    fund=source if corpus == CORPUS_MARKET_OPINION else None,
                    channel=CHANNEL_MBOX,
                    reliability_tier=reliability_tier,
                    recency_flag=recency_flag,
                    ingested_at=datetime.utcnow(),
                )
                db.add(doc)
                new_doc_ids.append((doc_id, content))
                imported += 1

            await db.commit()

            if new_doc_ids:
                import asyncio
                from backend.services import thesis_extractor
                from backend.db import SessionLocal

                _provider, _model = provider, model

                async def _extract_all():
                    for did, _content in new_doc_ids:
                        try:
                            async with SessionLocal() as bg_db:
                                await thesis_extractor.extract_and_save(
                                    did, _content, bg_db, provider=_provider, model=_model
                                )
                        except Exception:
                            pass
                        try:
                            async with SessionLocal() as bg_db:
                                result = await bg_db.execute(select(Document).where(Document.id == did))
                                _doc = result.scalar_one_or_none()
                                if _doc:
                                    await _async_index_document(_doc, _content)
                        except Exception:
                            pass

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
            channel = CHANNEL_FILE_UPLOAD
        else:
            content = raw.decode("utf-8", errors="replace")
            channel = CHANNEL_FILE_UPLOAD
    elif text:
        content = text
        channel = CHANNEL_MANUAL_PASTE
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

    corpus, source_type, reliability_tier = _classify_corpus(source)
    recency_flag = RECENCY_EVERGREEN if corpus == CORPUS_PRINCIPLES else RECENCY_TIMELY

    doc = Document(
        id=doc_id,
        source=source,
        title=title,
        content=content,
        date=date or None,
        processed=False,
        corpus=corpus,
        source_type=source_type,
        fund=source if corpus == CORPUS_MARKET_OPINION else None,
        channel=channel,
        reliability_tier=reliability_tier,
        recency_flag=recency_flag,
        ingested_at=datetime.utcnow(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    import asyncio
    from backend.services import thesis_extractor

    await thesis_extractor.extract_and_save(doc_id, content, db, provider=provider, model=model)
    await _async_index_document(doc, content)

    return {"status": "ok", "id": doc_id, "title": title}


# ── Perplexity ingest ──────────────────────────────────────────────────────────

class PerplexityIngestRequest(BaseModel):
    query: str
    topic: str


async def ingest_research_result(
    query: str,
    topic: str,
    content: str,
    citations: list[dict],
    db: AsyncSession,
    provider: str = "bedrock",
    model: Optional[str] = None,
) -> dict:
    """
    Persist an already-fetched Perplexity research result as a market_opinion
    document, then run thesis extraction and Chroma indexing.

    Shared by the /ingest-perplexity endpoint and the agent research flow so both
    land web research in the corpus through the same path. Returns a status dict.
    """
    if not content.strip():
        raise HTTPException(status_code=502, detail="Perplexity returned empty content.")

    doc_id = hashlib.sha256(content.encode()).hexdigest()[:32]

    existing = await db.execute(select(Document).where(Document.id == doc_id))
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "id": doc_id}

    # Generate tags via LLM
    tags = await _generate_tags(query, content, citations, provider=provider, model=model)

    expiration = datetime.utcnow() + timedelta(days=TTL_DAYS_WEB_RESEARCH)
    title = f"[Perplexity] {topic}: {query[:80]}"

    doc = Document(
        id=doc_id,
        source="perplexity",
        title=title,
        content=content,
        date=datetime.utcnow().strftime("%Y-%m-%d"),
        processed=False,
        corpus=CORPUS_MARKET_OPINION,
        source_type=SOURCE_TYPE_WEB_RESEARCH,
        fund=None,
        channel=CHANNEL_PERPLEXITY,
        reliability_tier=RELIABILITY_WEB_RESEARCH,
        recency_flag=RECENCY_TIMELY,
        expiration_at=expiration,
        citations_json=json.dumps(citations),
        ingested_at=datetime.utcnow(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    from backend.services import thesis_extractor

    extraction_result = await thesis_extractor.extract_and_save(
        doc_id, content, db, provider=provider, model=model
    )
    await _async_index_document(doc, content)

    return {
        "status": "ok",
        "id": doc_id,
        "title": title,
        "tags": tags,
        "citations_stored": len(citations),
        "expiration_at": expiration.isoformat(),
        "extraction": extraction_result,
    }


@router.post("/ingest-perplexity")
async def ingest_perplexity(
    req: PerplexityIngestRequest,
    provider: str = "bedrock",
    model: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Call Perplexity with `query`, persist the response as a market_opinion document,
    run thesis extraction and indexing, and return the created document id.

    Input: { query: str, topic: str }
    The backend generates tags via LLM from query + response content.
    TTL is set to 30 days for the web_research entry.
    """
    from backend.services import perplexity_client

    try:
        raw = await perplexity_client.research_raw(query=req.query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Perplexity request failed: {exc}")

    return await ingest_research_result(
        query=req.query,
        topic=req.topic,
        content=raw["content"],
        citations=raw["citations"],
        db=db,
        provider=provider,
        model=model,
    )


async def _generate_tags(
    query: str, content: str, citations: list[dict], provider: str = "bedrock", model: Optional[str] = None
) -> list[str]:
    """Ask the LLM to generate 3–7 short topic tags from query + content excerpt."""
    excerpt = content[:2000]
    prompt = (
        f"Generate 3 to 7 short topic tags (lowercase, no spaces, hyphen-separated if needed) "
        f"for the following research query and content. Return ONLY a JSON array of strings.\n\n"
        f"Query: {query}\n\nContent excerpt:\n{excerpt}"
    )
    try:
        if provider in ("ollama", "ollama-cloud"):
            from backend.services import ollama_client
            _model = model or (
                ollama_client.OLLAMA_CLOUD_DEFAULT_MODEL if provider == "ollama-cloud"
                else ollama_client.OLLAMA_DEFAULT_MODEL
            )
            host = ollama_client.OLLAMA_CLOUD_HOST if provider == "ollama-cloud" else None
            raw = await ollama_client.extract_json(excerpt, prompt, model=_model, host=host)
            if isinstance(raw, list):
                return [str(t) for t in raw]
            return []
        else:
            import asyncio, functools, boto3, os
            region = os.getenv("BEDROCK_REGION", "eu-west-1")
            model_id = model or os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
            client = boto3.client("bedrock-runtime", region_name=region)
            response = await asyncio.to_thread(
                functools.partial(
                    client.converse,
                    modelId=model_id,
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                )
            )
            text = ""
            for block in response.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    text = block["text"]
                    break
            if "```" in text:
                start = text.find("[", text.find("```"))
                end = text.rfind("]") + 1
                text = text[start:end] if start != -1 and end > start else text
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
            return []
    except Exception:
        return []


# ── Document listing & deletion ────────────────────────────────────────────────

@router.get("/documents")
async def list_documents(
    source: Optional[str] = None,
    corpus: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """List documents in the knowledge base, optionally filtered by source or corpus."""
    q = select(Document)
    if source:
        q = q.where(Document.source == source)
    if corpus:
        q = q.where(Document.corpus == corpus)
    q = q.order_by(Document.created_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "source": r.source,
            "date": r.date,
            "processed": r.processed,
            "corpus": r.corpus,
            "source_type": r.source_type,
            "fund": r.fund,
            "recency_flag": r.recency_flag,
            "reliability_tier": r.reliability_tier,
            "expiration_at": r.expiration_at.isoformat() if r.expiration_at else None,
        }
        for r in rows
    ]


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Remove a document, its extracted theses, and its Chroma chunks."""
    import asyncio
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    corpus = doc.corpus
    await db.delete(doc)
    await db.commit()

    if corpus == CORPUS_MARKET_OPINION:
        from backend.services.market_opinion_research import remove_document
        await asyncio.to_thread(remove_document, doc_id)
    else:
        from backend.services.research import remove_document_from_principles
        await asyncio.to_thread(remove_document_from_principles, doc_id)

    return {"status": "deleted"}


# ── Thesis search ──────────────────────────────────────────────────────────────

@router.get("/theses")
async def get_theses(
    entity: Optional[str] = None,
    theme: Optional[str] = None,
    fund: Optional[str] = None,
    source_type: Optional[str] = None,
    recency_flag: Optional[str] = None,
    exclude_stale: bool = False,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    """Query the structured thesis database with optional taxonomy filters."""
    return await knowledge_base.search_theses(
        entity, theme, limit, db,
        fund=fund, source_type=source_type,
        recency_flag=recency_flag, exclude_stale=exclude_stale,
    )


@router.get("/entity/{symbol}")
async def get_entity(symbol: str, db: AsyncSession = Depends(get_db)):
    """Get the entity graph (suppliers, competitors, customers) for a ticker."""
    return await knowledge_base.get_entity_graph(symbol, db)


# ── Search endpoints ───────────────────────────────────────────────────────────

@router.get("/search")
async def search_docs(q: str, limit: int = 8):
    """Hybrid semantic + keyword search over the principles library."""
    from backend.services.research import search_principles
    return search_principles(q, top_k=limit)


@router.get("/search-market-opinion")
async def search_market_opinion_docs(
    q: str,
    limit: int = 8,
    fund: Optional[str] = None,
    source_type: Optional[str] = None,
):
    """Semantic search over the market-opinion collection (all funds + Perplexity web research)."""
    from backend.services.market_opinion_research import search_market_opinion
    return search_market_opinion(q, top_k=limit, fund=fund, source_type=source_type)


# ── Reindex endpoints ──────────────────────────────────────────────────────────

@router.post("/reindex")
async def reindex_principles():
    """Admin: force a full re-index of the investing_research/ library into chromadb."""
    import asyncio
    from backend.services.research import rebuild_index
    count = await asyncio.to_thread(rebuild_index)
    return {"status": "ok", "chunks_indexed": count}


@router.post("/reindex-market")
async def reindex_market_opinion():
    """Admin: force a full re-index of all market_opinion documents from DB into chromadb."""
    from backend.services.market_opinion_research import rebuild_market_opinion_index
    count = await rebuild_market_opinion_index()
    return {"status": "ok", "chunks_indexed": count}


# ── Stale cleanup ──────────────────────────────────────────────────────────────

@router.delete("/cleanup-stale")
async def cleanup_stale(db: AsyncSession = Depends(get_db)):
    """Remove all market_opinion documents whose expiration_at has passed."""
    import asyncio
    from backend.services.market_opinion_research import remove_document
    result = await db.execute(
        select(Document).where(
            Document.corpus == CORPUS_MARKET_OPINION,
            Document.expiration_at != None,  # noqa: E711
            Document.expiration_at <= datetime.utcnow(),
        )
    )
    stale_docs = result.scalars().all()
    removed = 0
    for doc in stale_docs:
        await db.delete(doc)
        await asyncio.to_thread(remove_document, doc.id)
        removed += 1
    await db.commit()
    return {"status": "ok", "removed": removed}
