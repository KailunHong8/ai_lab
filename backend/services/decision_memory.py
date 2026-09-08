"""Decision memory — record proposals and reflect on realized returns."""
from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.types import TradeProposalResult


async def record(db: AsyncSession, result: TradeProposalResult, price: float) -> None:
    from backend.models import DecisionMemory
    decision_date = date.fromisoformat(result.analysis_date)
    mem = DecisionMemory(
        id=str(uuid.uuid4()),
        symbol=result.symbol,
        action=result.trader_decision.action,
        decision_date=str(decision_date),
        price_at_decision=price,
        proposal_id=result.proposal_id,
        horizon_date=str(decision_date + timedelta(days=30)),
    )
    db.add(mem)
    await db.commit()


async def get_prior_reflection(db: AsyncSession, symbol: str) -> str | None:
    """Return the most recent reflection for a symbol, if any."""
    from backend.models import DecisionMemory
    stmt = (
        select(DecisionMemory)
        .where(DecisionMemory.symbol == symbol)
        .where(DecisionMemory.reflection.isnot(None))
        .order_by(DecisionMemory.decision_date.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row.reflection if row else None


async def check_and_reflect(db: AsyncSession, symbol: str, provider: str, model: str | None) -> None:
    """Check if any prior decisions have reached their horizon and reflect on them."""
    from backend.models import DecisionMemory
    from backend.services import market_data, llm

    today = str(date.today())
    stmt = (
        select(DecisionMemory)
        .where(DecisionMemory.symbol == symbol)
        .where(DecisionMemory.horizon_date <= today)
        .where(DecisionMemory.reflection.is_(None))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    for row in rows:
        try:
            current_quote = await market_data.get_quote(symbol)
            spy_quote = await market_data.get_quote("SPY")
            if row.price_at_decision and current_quote.price:
                row.realized_return = round(
                    (current_quote.price - row.price_at_decision) / row.price_at_decision * 100, 2
                )
            # SPY return approximation: we don't have the historical price, skip for now
            system = (
                "You are a self-reflecting trading analyst. Given a prior decision and its realized outcome, "
                "identify what the analysis got right and what it missed. Be concise and honest."
            )
            user = (
                f"Prior decision: {row.action} {symbol} on {row.decision_date} at ${row.price_at_decision:.2f}.\n"
                f"Current price: ${current_quote.price:.2f}.\n"
                f"Realized return: {row.realized_return:.1f}% over 30 days.\n\n"
                "What did the analysis get right? Where did it fail? 2-3 sentences."
            )
            row.reflection = await llm.complete(system, user, provider, model)
            row.reflected_at = today
            await db.commit()
        except Exception:
            pass
