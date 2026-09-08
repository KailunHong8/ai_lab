"""
Decision ledger service — records AI-assisted paper-trading decisions.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Decision


async def record_decision(
    db: AsyncSession,
    *,
    action: str,
    symbol: str,
    shares: Optional[float] = None,
    price: Optional[float] = None,
    transaction_id: Optional[int] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    session_id: Optional[str] = None,
    thesis_ids: Optional[list[str]] = None,
    document_ids: Optional[list[str]] = None,
    strategy_text: Optional[str] = None,
    strategy_parsed: Optional[dict] = None,
    simulation_run_id: Optional[str] = None,
    confirmed_by_user: bool = False,
) -> str:
    """Persist a Decision row and return its id."""
    decision_id = str(uuid.uuid4())
    decision = Decision(
        id=decision_id,
        action=action.upper(),
        symbol=symbol.upper(),
        shares=shares,
        price=price,
        transaction_id=transaction_id,
        provider=provider,
        model=model,
        session_id=session_id,
        thesis_ids_json=json.dumps(thesis_ids) if thesis_ids else None,
        document_ids_json=json.dumps(document_ids) if document_ids else None,
        strategy_text=strategy_text,
        strategy_parsed_json=json.dumps(strategy_parsed) if strategy_parsed else None,
        simulation_run_id=simulation_run_id,
        confirmed_by_user=confirmed_by_user,
    )
    db.add(decision)
    await db.commit()
    return decision_id
