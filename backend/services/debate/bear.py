"""Bear researcher agent — constructs the strongest bearish thesis."""
from __future__ import annotations

import json

from backend.services.llm import complete, extract_json
from backend.services.types import AnalystReport, ResearchCase

_SYSTEM = (
    "You are a bear-case researcher. Given analyst reports, build the strongest bearish thesis. "
    "Lead with valuation, momentum, or macro headwinds. Challenge the bull case directly. "
    "Respond ONLY with a valid JSON object — no markdown."
)

_USER_TEMPLATE = """
Build the bear case for {symbol}.

Analyst reports:
{reports}

{prior_bull}

Return JSON with these exact keys:
{{
  "thesis": "1-2 sentence core bear thesis",
  "supporting_points": ["point 1", "point 2", "point 3"],
  "key_risk_acknowledged": "the most important bull risk and your rebuttal",
  "confidence": "LOW" | "MEDIUM" | "HIGH"
}}
"""


async def run(
    symbol: str,
    reports: list[AnalystReport],
    provider: str,
    model: str | None,
    prior_bull: ResearchCase | None = None,
) -> ResearchCase:
    reports_text = json.dumps([r.model_dump() for r in reports], indent=2)
    bull_section = ""
    if prior_bull:
        bull_section = f"\nBull case to rebut:\n{json.dumps(prior_bull.model_dump(), indent=2)}\n"

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        reports=reports_text,
        prior_bull=bull_section,
    )

    try:
        text = await complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    return ResearchCase(
        side="bear",
        symbol=symbol,
        thesis=parsed.get("thesis", "Bearish on " + symbol),
        supporting_points=parsed.get("supporting_points", []),
        key_risk_acknowledged=parsed.get("key_risk_acknowledged", ""),
        confidence=parsed.get("confidence", "MEDIUM"),
    )


async def rebut(
    current: ResearchCase,
    opponent: ResearchCase,
    provider: str,
    model: str | None,
) -> ResearchCase:
    """Produce a rebuttal bear case given the bull's response."""
    return await run(current.symbol, [], provider, model, prior_bull=opponent)
