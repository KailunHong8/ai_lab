"""Trader agent — synthesizes all research into a typed trade decision."""
from __future__ import annotations

import json

from backend.services.llm import complete, extract_json
from backend.services.types import AnalystReport, PortfolioSnapshot, ResearchCase, TraderDecision

_SYSTEM = (
    "You are a portfolio trader. You receive research from three analysts and two researchers. "
    "Weigh the evidence and issue a typed trade decision. Maximize decision quality — "
    "risk management is handled separately. "
    "Respond ONLY with a valid JSON object — no markdown."
)

_USER_TEMPLATE = """
Issue a trade decision for {symbol}.

Analyst reports:
{reports}

Bull case:
{bull}

Bear case:
{bear}

Current portfolio:
{portfolio}

Return JSON with these exact keys:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": "LOW" | "MEDIUM" | "HIGH",
  "rationale": "2-3 sentences citing specific analyst evidence",
  "suggested_size_pct": <float 0-25, percent of portfolio value; 0 for HOLD or SELL>,
  "time_horizon": "short" | "medium" | "long"
}}
"""


async def run(
    symbol: str,
    reports: list[AnalystReport],
    bull: ResearchCase,
    bear: ResearchCase,
    portfolio: PortfolioSnapshot,
    provider: str,
    model: str | None,
) -> TraderDecision:
    portfolio_summary = {
        "total_value": portfolio.total_value,
        "cash_pct": portfolio.cash_pct,
        "current_position": next(
            (h for h in portfolio.holdings if h.get("symbol") == symbol), None
        ),
    }

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        reports=json.dumps([r.model_dump() for r in reports], indent=2),
        bull=json.dumps(bull.model_dump(), indent=2),
        bear=json.dumps(bear.model_dump(), indent=2),
        portfolio=json.dumps(portfolio_summary, indent=2),
    )

    try:
        text = await complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    size = float(parsed.get("suggested_size_pct", 0))
    size = max(0.0, min(25.0, size))

    return TraderDecision(
        action=parsed.get("action", "HOLD"),
        confidence=parsed.get("confidence", "LOW"),
        rationale=parsed.get("rationale", ""),
        suggested_size_pct=size,
        time_horizon=parsed.get("time_horizon", "medium"),
    )
