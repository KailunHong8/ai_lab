"""Risk manager — deterministic checks + LLM commentary."""
from __future__ import annotations

import json

from backend.services.llm import complete
from backend.services.types import PortfolioSnapshot, RiskFlag, RiskResult, TraderDecision

_SYSTEM = (
    "You are a risk manager reviewing a proposed trade. Given the risk flags and portfolio context, "
    "write a 2-sentence risk commentary. Be direct. Respond with plain text only."
)


def check_risk(decision: TraderDecision, portfolio: PortfolioSnapshot, symbol: str) -> list[RiskFlag]:
    flags: list[RiskFlag] = []

    if decision.action == "BUY":
        pct = decision.suggested_size_pct

        if pct > 20:
            flags.append(RiskFlag(
                code="CONCENTRATION_HIGH",
                severity="block",
                message=f"Proposed {pct:.1f}% allocation exceeds 20% concentration limit.",
            ))

        sector = next(
            (h.get("sector", "") for h in portfolio.holdings if h.get("symbol") == symbol),
            "",
        )
        if sector:
            sector_weight = portfolio.sector_weights.get(sector, 0.0)
            if sector_weight > 35:
                flags.append(RiskFlag(
                    code="SECTOR_OVERWEIGHT",
                    severity="warn",
                    message=f"{sector} sector already at {sector_weight:.1f}% of portfolio.",
                ))

        if portfolio.cash_pct < pct + 5:
            flags.append(RiskFlag(
                code="INSUFFICIENT_CASH",
                severity="block",
                message=(
                    f"Insufficient cash: {portfolio.cash_pct:.1f}% available, "
                    f"need {pct + 5:.1f}% (allocation + 5% buffer)."
                ),
            ))

    return flags


async def run(
    symbol: str,
    decision: TraderDecision,
    portfolio: PortfolioSnapshot,
    prior_reflection: str | None,
    provider: str,
    model: str | None,
) -> RiskResult:
    flags = check_risk(decision, portfolio, symbol)
    approved = all(f.severity != "block" for f in flags)

    flags_text = "\n".join(f"- [{f.severity.upper()}] {f.code}: {f.message}" for f in flags) or "No flags."
    prior_text = f"\nPrior decision reflection:\n{prior_reflection}" if prior_reflection else ""

    user_msg = (
        f"Trade proposal: {decision.action} {symbol} at {decision.suggested_size_pct:.1f}% of portfolio.\n"
        f"Confidence: {decision.confidence}. Rationale: {decision.rationale}\n\n"
        f"Risk flags:\n{flags_text}{prior_text}\n\n"
        f"Portfolio: total ${portfolio.total_value:,.0f}, cash {portfolio.cash_pct:.1f}%."
    )

    try:
        commentary = await complete(_SYSTEM, user_msg, provider, model)
        commentary = commentary.strip()
    except Exception:
        commentary = "Risk assessment unavailable."

    return RiskResult(approved=approved, flags=flags, commentary=commentary)
