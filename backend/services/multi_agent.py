"""Multi-agent orchestrator — runs the full trading analysis pipeline."""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.types import PortfolioSnapshot, TradeProposalResult


async def _get_portfolio_snapshot(db: AsyncSession) -> PortfolioSnapshot:
    from backend.routers.portfolio import summary as portfolio_summary
    data = await portfolio_summary(db=db)
    holdings = []
    sector_weights: dict[str, float] = {}
    total = float(data.get("total_value", 0) or 0)
    cash = float(data.get("cash_balance", 0) or 0)
    cash_pct = (cash / total * 100) if total > 0 else 100.0

    for h in data.get("holdings", []):
        val = float(h.get("market_value", 0) or 0)
        weight = (val / total * 100) if total > 0 else 0.0
        sector = h.get("sector") or "Unknown"
        holdings.append({
            "symbol": h.get("symbol", ""),
            "shares": h.get("shares"),
            "value": val,
            "weight_pct": round(weight, 2),
            "sector": sector,
        })
        sector_weights[sector] = sector_weights.get(sector, 0.0) + weight

    return PortfolioSnapshot(
        total_value=total,
        cash=cash,
        cash_pct=round(cash_pct, 2),
        holdings=holdings,
        sector_weights={k: round(v, 2) for k, v in sector_weights.items()},
    )


async def run(
    symbol: str,
    analysis_date: date,
    provider: str,
    model: str | None,
    session_id: str,
    db: AsyncSession,
    debate_rounds: int = 1,
) -> TradeProposalResult:
    """Run the full pipeline and return the result. No streaming."""
    async for _event, result in _run_streaming(
        symbol, analysis_date, provider, model, session_id, db, debate_rounds
    ):
        if result is not None:
            return result
    raise RuntimeError("Pipeline produced no result")


async def run_streaming(
    symbol: str,
    analysis_date: date,
    provider: str,
    model: str | None,
    session_id: str,
    db: AsyncSession,
    debate_rounds: int = 1,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings as each phase completes."""
    async for event_data, result in _run_streaming(
        symbol, analysis_date, provider, model, session_id, db, debate_rounds
    ):
        yield f"data: {json.dumps(event_data)}\n\n"


async def _run_streaming(
    symbol: str,
    analysis_date: date,
    provider: str,
    model: str | None,
    session_id: str,
    db: AsyncSession,
    debate_rounds: int,
):
    from backend.services.analyst import fundamentals as fa, technical as ta, sentiment as sa
    from backend.services.debate import bull as bull_agent, bear as bear_agent
    from backend.services import trader as trader_agent, risk_manager, decision_memory, market_data
    from backend.models import TradeProposal

    symbol = symbol.upper()

    # Phase 1: parallel analysts
    yield {"phase": "analysts", "status": "running", "symbol": symbol}, None
    fundamentals_r, technical_r, sentiment_r = await asyncio.gather(
        fa.run(symbol, analysis_date, provider, model),
        ta.run(symbol, analysis_date, provider, model),
        sa.run(symbol, analysis_date, provider, model),
    )
    reports = [fundamentals_r, technical_r, sentiment_r]
    yield {
        "phase": "analysts",
        "status": "complete",
        "preview": {
            "valuation": fundamentals_r.valuation_signal,
            "trend": technical_r.trend,
            "news_tone": sentiment_r.news_tone,
        },
    }, None

    # Phase 2: bull/bear debate
    yield {"phase": "debate", "status": "running"}, None
    bull = await bull_agent.run(symbol, reports, provider, model)
    bear = await bear_agent.run(symbol, reports, provider, model)
    for _ in range(debate_rounds - 1):
        bull = await bull_agent.rebut(bull, bear, provider, model)
        bear = await bear_agent.rebut(bear, bull, provider, model)
    yield {
        "phase": "debate",
        "status": "complete",
        "preview": {
            "bull_confidence": bull.confidence,
            "bear_confidence": bear.confidence,
        },
    }, None

    # Phase 3: trader
    yield {"phase": "trader", "status": "running"}, None
    portfolio = await _get_portfolio_snapshot(db)
    decision = await trader_agent.run(symbol, reports, bull, bear, portfolio, provider, model)
    yield {
        "phase": "trader",
        "status": "complete",
        "preview": {"action": decision.action, "confidence": decision.confidence},
    }, None

    # Phase 4: risk gate
    yield {"phase": "risk", "status": "running"}, None
    await decision_memory.check_and_reflect(db, symbol, provider, model)
    prior_reflection = await decision_memory.get_prior_reflection(db, symbol)
    risk = await risk_manager.run(symbol, decision, portfolio, prior_reflection, provider, model)
    yield {
        "phase": "risk",
        "status": "complete",
        "preview": {"approved": risk.approved, "flags": len(risk.flags)},
    }, None

    # Phase 5: persist
    proposal_id = str(uuid.uuid4())
    result = TradeProposalResult(
        proposal_id=proposal_id,
        symbol=symbol,
        analysis_date=str(analysis_date),
        fundamentals_report=fundamentals_r,
        technical_report=technical_r,
        sentiment_report=sentiment_r,
        bull_case=bull,
        bear_case=bear,
        trader_decision=decision,
        risk_result=risk,
    )

    try:
        quote = await market_data.get_quote(symbol)
        price = quote.price
    except Exception:
        price = 0.0

    db.add(TradeProposal(
        id=proposal_id,
        symbol=symbol,
        analysis_date=str(analysis_date),
        session_id=session_id or None,
        provider=provider,
        model=model,
        result_json=result.model_dump_json(),
        action=decision.action,
        confidence=decision.confidence,
        risk_approved=risk.approved,
    ))
    await db.commit()

    await decision_memory.record(db, result, price)

    yield {"phase": "complete", "status": "complete", "result": result.model_dump()}, result
