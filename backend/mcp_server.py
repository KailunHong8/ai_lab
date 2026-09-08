"""MCP server — exposes Quant's tools to Claude Code and MCP-compatible assistants."""
from __future__ import annotations

import asyncio
import os
from datetime import date

from fastmcp import FastMCP

mcp = FastMCP("Quant Trading Intelligence")


@mcp.tool()
async def analyze_ticker(symbol: str, analysis_date: str | None = None) -> dict:
    """Run full multi-agent analysis: fundamentals, technical, sentiment, bull/bear debate,
    risk gate. Returns a typed trade proposal."""
    from backend.db import SessionLocal
    from backend.services.multi_agent import run

    _date = date.fromisoformat(analysis_date) if analysis_date else date.today()
    provider = os.getenv("MCP_PROVIDER", "bedrock")
    model = os.getenv("MCP_MODEL") or None

    async with SessionLocal() as db:
        result = await run(
            symbol=symbol.upper(),
            analysis_date=_date,
            provider=provider,
            model=model,
            session_id="mcp",
            db=db,
        )
    return result.model_dump()


@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """Real-time stock quote (price, change, volume, market cap)."""
    from backend.services.market_data import get_quote as _get_quote
    quote = await _get_quote(symbol.upper())
    return quote.model_dump()


@mcp.tool()
async def get_fundamentals(symbol: str) -> dict:
    """Company fundamentals: P/E, EPS, revenue, margins, debt/equity."""
    from backend.services.market_data import get_fundamentals as _get_fund
    fund = await _get_fund(symbol.upper())
    return fund.model_dump()


@mcp.tool()
async def get_macro_context() -> dict:
    """Current macroeconomic snapshot: Fed rate, CPI, yield curve, VIX."""
    from backend.services.fred import get_macro_snapshot
    snap = await get_macro_snapshot()
    return snap.model_dump()


@mcp.tool()
async def get_portfolio_summary() -> dict:
    """Current paper portfolio: holdings, cash, total value, sector exposure."""
    from backend.db import SessionLocal
    from backend.routers.portfolio import summary

    async with SessionLocal() as db:
        return await summary(db=db)


@mcp.tool()
async def get_decision_history(symbol: str | None = None) -> list[dict]:
    """Prior trade proposals and realized outcomes. Optionally filtered by symbol."""
    from backend.db import SessionLocal
    from backend.models import TradeProposal, DecisionMemory
    from sqlalchemy import select

    async with SessionLocal() as db:
        stmt = select(DecisionMemory).order_by(DecisionMemory.decision_date.desc()).limit(20)
        if symbol:
            stmt = stmt.where(DecisionMemory.symbol == symbol.upper())
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "symbol": r.symbol,
                "action": r.action,
                "decision_date": r.decision_date,
                "price_at_decision": r.price_at_decision,
                "realized_return": r.realized_return,
                "reflection": r.reflection,
            }
            for r in rows
        ]


@mcp.tool()
async def screen_stocks(
    min_pe: float | None = None,
    max_pe: float | None = None,
    min_roe: float | None = None,
    sector: str | None = None,
) -> list[str]:
    """Screen for tickers matching value criteria. Returns list of matching symbols."""
    from backend.db import SessionLocal
    from backend.models import ScreenerResult
    from sqlalchemy import select

    async with SessionLocal() as db:
        stmt = select(ScreenerResult).where(ScreenerResult.passes_screen == True).limit(200)
        result = await db.execute(stmt)
        rows = result.scalars().all()

    out: list[str] = []
    for r in rows:
        f = r.fundamentals or {}
        if min_pe is not None and (f.get("pe_ratio") or 0) < min_pe:
            continue
        if max_pe is not None and (f.get("pe_ratio") or 9999) > max_pe:
            continue
        if min_roe is not None and (f.get("roe") or 0) < min_roe:
            continue
        if sector and (r.sector or "").lower() != sector.lower():
            continue
        if r.symbol not in out:
            out.append(r.symbol)

    return out[:50]


if __name__ == "__main__":
    mcp.run()
