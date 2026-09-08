from __future__ import annotations

import asyncio
import functools
import os
from typing import Optional

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import ChatSession, ChatMessage
from backend.routers.portfolio import summary as portfolio_summary
from backend.routers.sessions import append_messages
from backend.services import bedrock

router = APIRouter(prefix="/api/agent", tags=["agent"])

_TITLE_SYSTEM = (
    "You are a session title generator. "
    "Given a user's first message to a trading copilot, respond with a short title (4–7 words, title case, no punctuation). "
    "Only output the title — nothing else."
)


async def _generate_title(message: str) -> str:
    """Generate a short session title via Bedrock (fast, fire-and-forget on error)."""
    try:
        import boto3
        from botocore.config import Config
        region = os.getenv("BEDROCK_REGION", "eu-west-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
        client = boto3.client("bedrock-runtime", region_name=region, config=Config(read_timeout=30))
        resp = await asyncio.to_thread(
            functools.partial(
                client.converse,
                modelId=model_id,
                system=[{"text": _TITLE_SYSTEM}],
                messages=[{"role": "user", "content": [{"text": message}]}],
            )
        )
        return resp["output"]["message"]["content"][0]["text"].strip()
    except Exception:
        words = message.split()
        return " ".join(words[:6]) + ("…" if len(words) > 6 else "")


class ChatRequest(BaseModel):
    message: str
    session_id: str              # must be a valid session UUID from /api/sessions
    provider: str = "bedrock"
    model: Optional[str] = None
    agent_mode: str = "auto"     # auto = orchestrator routes; advice | research force a specialist


async def _advice_reply(
    message: str,
    history: list[dict],
    portfolio: dict | None,
    provider: str,
    model: Optional[str],
    session_id: str,
) -> str:
    """Run the tool-equipped advice agent on the user's configured provider."""
    if provider == "ollama":
        from backend.services import ollama_client
        _model = model or ollama_client.OLLAMA_DEFAULT_MODEL
        return await ollama_client.chat(
            message=message,
            history=history,
            portfolio_snapshot=portfolio,
            model=_model,
            session_id=session_id,
        )
    elif provider == "ollama-cloud":
        from backend.services import ollama_client
        _api_key = os.getenv("OLLAMA_API_KEY", "")
        if not _api_key:
            raise HTTPException(status_code=503, detail="OLLAMA_API_KEY is not set. Add it to .env to use Ollama Cloud.")
        _model = model or ollama_client.OLLAMA_CLOUD_DEFAULT_MODEL
        return await ollama_client.chat(
            message=message,
            history=history,
            portfolio_snapshot=portfolio,
            model=_model,
            session_id=session_id,
            host=ollama_client.OLLAMA_CLOUD_HOST,
            api_key=_api_key,
        )
    else:
        return await bedrock.chat(
            message=message,
            history=history,
            portfolio_snapshot=portfolio,
            session_id=session_id,
        )


async def _research_reply(
    message: str,
    history: list[dict],
    session_id: str,
    provider: str,
    model: Optional[str],
    db: AsyncSession,
) -> str:
    """
    Run a Perplexity research turn and ingest the result into the market_opinion
    corpus (same path as /ingest-perplexity), so chat research is persisted,
    thesis-extracted, and indexed. Returns the reply text with a Sources footer.
    """
    from backend.services import perplexity_client
    from backend.routers.knowledge import ingest_research_result

    try:
        raw = await perplexity_client.research_raw(
            query=message, history=history, session_id=session_id
        )
    except Exception:
        # Transport failure — fall back to the plain research turn (handles its
        # own error messaging) and skip ingestion.
        return await perplexity_client.research(
            message=message, history=history, session_id=session_id
        )

    content = raw["content"]
    if not content.strip():
        return "Research provider returned an unexpected response."

    # Persist + extract + index; never let an ingestion hiccup block the reply.
    try:
        await ingest_research_result(
            query=message, topic="chat", content=content, citations=raw["citations"],
            db=db, provider=provider, model=model,
        )
    except Exception as exc:
        import structlog as _sl
        _sl.get_logger("agent.research_ingest").error("ingest_failed", error=str(exc))

    return content + perplexity_client.format_citations_footer(raw["citations"])


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    from backend.services import orchestrator

    # Load session + history from DB
    session = await db.get(ChatSession, req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Create one via POST /api/sessions first.")

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == req.session_id)
        .order_by(ChatMessage.sequence)
    )
    result = await db.execute(stmt)
    msgs = result.scalars().all()
    history = [{"role": m.role, "content": m.content} for m in msgs]

    portfolio = await portfolio_summary(db=db)

    # Orchestrator: decide which specialist answers.
    if req.agent_mode in ("advice", "research"):
        intent = req.agent_mode
    else:
        intent = await orchestrator.classify_intent(req.message)

    if intent == "research":
        reply = await _research_reply(
            req.message, history, req.session_id, req.provider, req.model, db
        )
    elif intent == "both":
        findings = await _research_reply(
            req.message, history, req.session_id, req.provider, req.model, db
        )
        synthesis_input = orchestrator.build_synthesis_input(req.message, findings)
        reply = await _advice_reply(
            synthesis_input, history, portfolio, req.provider, req.model, req.session_id
        )
    else:
        reply = await _advice_reply(
            req.message, history, portfolio, req.provider, req.model, req.session_id
        )

    # Auto-title on the very first user message (skip the system-init turn at seq 1-2)
    stmt_count = select(ChatMessage).where(ChatMessage.session_id == req.session_id)
    count_result = await db.execute(stmt_count)
    msg_count = len(count_result.scalars().all())
    if not session.name and msg_count <= 2:
        title = await _generate_title(req.message)
        session.name = title
        await db.commit()

    await append_messages(
        session_id=req.session_id,
        user_content=[{"text": req.message}],
        assistant_content=[{"text": reply}],
        db=db,
    )

    return {"reply": reply, "session_id": req.session_id, "session_name": session.name, "intent": intent}


# ── Multi-agent run ────────────────────────────────────────────────────────────

class MultiRunRequest(BaseModel):
    symbol: str
    analysis_date: Optional[str] = None    # defaults to today
    session_id: str = ""
    provider: str = "bedrock"
    model: Optional[str] = None
    debate_rounds: int = 1


@router.post("/multi-run")
async def multi_run(req: MultiRunRequest, db: AsyncSession = Depends(get_db)):
    from backend.services.multi_agent import run_streaming

    analysis_date = date.fromisoformat(req.analysis_date) if req.analysis_date else date.today()

    async def _generate():
        try:
            async for chunk in run_streaming(
                symbol=req.symbol,
                analysis_date=analysis_date,
                provider=req.provider,
                model=req.model,
                session_id=req.session_id,
                db=db,
                debate_rounds=max(1, min(3, req.debate_rounds)),
            ):
                yield chunk
        except Exception as exc:
            import json
            yield f"data: {json.dumps({'phase': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(_generate(), media_type="text/event-stream")


@router.get("/proposals")
async def list_proposals(symbol: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from backend.models import TradeProposal
    import json as _json

    stmt = select(TradeProposal).order_by(TradeProposal.created_at.desc()).limit(50)
    if symbol:
        stmt = stmt.where(TradeProposal.symbol == symbol.upper())
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return {
        "proposals": [
            {
                "id": r.id,
                "symbol": r.symbol,
                "analysis_date": r.analysis_date,
                "action": r.action,
                "confidence": r.confidence,
                "risk_approved": r.risk_approved,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }
