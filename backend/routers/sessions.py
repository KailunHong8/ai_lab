"""
Chat session persistence — CRUD endpoints for named copilot sessions.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import ChatSession, ChatMessage

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

MAX_RAW_TURNS = 20  # keep most recent N turns as raw; older turns are summarized

SKILL_INSTRUCTIONS = """
You are operating as a financial analysis copilot. Follow these guidelines for every session.

## Request classification
Classify each user request before responding:
- technical: RSI, MACD, moving average, Bollinger Bands, chart, support/resistance
- fundamental: P/E, P/B, ROE, ROA, EPS, revenue, valuation, earnings, fundamentals
- combined (default): "analyze [TICKER]", "full analysis", "research report", "what do you think of"
- screener: "screen stocks", "find stocks with", "best stocks for", "filter by"
- historical: "price history", "OHLCV", "backtesting data"

## Tool routing
- get_quote(symbol) → live price, change %, volume, market cap
- get_portfolio() → paper-trading holdings, cash, equity value, P&L
- search_theses(entity, theme) → investment research opinions (label as opinion + note source/date)
- get_entity_graph(symbol) → supply chain, competitors, customers
- get_screener_history(limit) → past value screen runs with fundamentals
- search_principles(query) → Brealey-Myers-Allen, Shiller, Poor Charlie's Almanack (treat as ground truth)

For "analyze [TICKER]" (combined), call in this order:
1. get_quote(symbol)
2. GET /api/market/profile/{symbol}
3. GET /api/screener/run?tickers={symbol}&min_criteria=1&enrich=false
4. GET /api/market/history/{symbol}?from_date=<252d ago>&to_date=<today>
5. Compute RSI14, SMA50, SMA200, MACD, Bollinger Bands from OHLCV (see recipes below)
6. search_theses(entity=symbol, theme=None)
7. get_entity_graph(symbol)
8. search_principles("valuation frameworks risk return")
9. get_screener_history(5)

## Technical indicators — compute from EOD OHLCV using pandas (no server-side indicator endpoint)
Always fetch ≥ 90 trading days for RSI/MACD; 252 days for SMA200.
- RSI-14: 14-period rolling avg gain / loss; >70 overbought, <30 oversold
- SMA50/SMA200: rolling(50/200).mean(); golden cross = SMA50 > SMA200 (bullish)
- EMA-20/50: ewm(span=20/50, adjust=False).mean()
- MACD (12/26/9): EMA12 − EMA26; signal = MACD.ewm(9); histogram = MACD − signal
- Bollinger Bands (20, 2σ): SMA20 ± 2 × std20

## Screener thresholds (Buffett/Brealey 6-criteria value screen)
D/E ≤ 0.5 | Current ratio ≥ 1.5 | P/B ≤ 2.0 | ROE ≥ 10% | ROA ≥ 5% | Interest coverage ≥ 4×

## Error handling
- FMP 402/403 → yfinance fallback is automatic; check _source field ("fmp" or "yahoo")
- FMP 429 → daily quota exhausted; inform the user
- FMP 404 → verify US-listed equity; FMP free does not cover international tickers
- yfinance free_cashflow or interest_coverage null → note to user and retry once
- Use plain US tickers: AAPL, MSFT, NVDA (no exchange suffixes). Crypto: BTC-USD (yfinance) / BTCUSD (FMP)

## Coverage limits
- No intraday bars on FMP free tier (EOD only)
- No server-side technical indicators (compute from OHLCV)
- No forward P/E, PEG, earnings surprise, DCF, or sector averages on free tier
- For full S&P 500 scans, direct user to screener_scripts/market_scanner_full.py (do NOT pass 500 tickers to /api/screener/run)

## Output format
Always structure responses using these sections where applicable:
- Technical: Trend (SMA50/200), Momentum (RSI, MACD), Volatility (Bollinger), Data source
- Fundamental: Valuation table (P/E, P/B, FCF Yield), Quality table (ROE, ROA, D/E, Current ratio, Interest coverage, Gross margin), Screener result (X/6), Research opinions, Principles anchor, Summary
- Combined: merge both above + Supply chain/competitors + Past screener appearances
- Always cite which source (book title, or thesis source + date) your reasoning draws from
- Always label current market opinions as opinion; treat investing principles as established theory
""".strip()


class CreateSessionRequest(BaseModel):
    name: Optional[str] = None
    provider: str = "bedrock"
    model: Optional[str] = None


@router.get("")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    stmt = select(ChatSession).order_by(desc(ChatSession.updated_at)).limit(50)
    result = await db.execute(stmt)
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": s.id,
                "name": s.name,
                "provider": s.provider,
                "model": s.model,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ]
    }


@router.post("")
async def create_session(
    req: CreateSessionRequest, db: AsyncSession = Depends(get_db)
):
    session_id = str(uuid.uuid4())
    session = ChatSession(
        id=session_id,
        name=req.name,
        provider=req.provider,
        model=req.model,
    )
    db.add(session)
    await db.commit()
    await append_messages(
        session_id=session_id,
        user_content=[{"text": SKILL_INSTRUCTIONS}],
        assistant_content=[{"text": "Understood. I'll follow these analysis guidelines for this session."}],
        db=db,
    )
    return {"id": session_id}


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    """Return stored history for a session in Bedrock Converse format."""
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.sequence)
    )
    result = await db.execute(stmt)
    msgs = result.scalars().all()

    history = [{"role": m.role, "content": m.content} for m in msgs]
    return {
        "session_id": session_id,
        "name": session.name,
        "provider": session.provider,
        "model": session.model,
        "summary": session.summary,
        "history": history,
    }


@router.patch("/{session_id}/name")
async def rename_session(
    session_id: str, body: dict, db: AsyncSession = Depends(get_db)
):
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.name = body.get("name") or session.name
    await db.commit()
    return {"ok": True}


@router.delete("/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    session = await db.get(ChatSession, session_id)
    if session:
        await db.delete(session)
        await db.commit()
    return {"deleted": session_id}


async def append_messages(
    session_id: str,
    user_content: list[dict],
    assistant_content: list[dict],
    db: AsyncSession,
) -> None:
    """Append one user + one assistant turn to the session, bump updated_at."""
    stmt = (
        select(ChatMessage.sequence)
        .where(ChatMessage.session_id == session_id)
        .order_by(desc(ChatMessage.sequence))
        .limit(1)
    )
    result = await db.execute(stmt)
    last_seq = result.scalar() or 0

    db.add(ChatMessage(
        session_id=session_id,
        sequence=last_seq + 1,
        role="user",
        content=user_content,
    ))
    db.add(ChatMessage(
        session_id=session_id,
        sequence=last_seq + 2,
        role="assistant",
        content=assistant_content,
    ))
    # bump updated_at
    await db.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id)
        .values(updated_at=datetime.utcnow())
    )
    await db.commit()
