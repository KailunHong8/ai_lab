"""Bull researcher agent — constructs the strongest bullish thesis."""
from __future__ import annotations

import json

from backend.services.llm import complete, extract_json
from backend.services.types import AnalystReport, ResearchCase

_SYSTEM = (
    "You are a bull-case researcher. Given analyst reports, build the strongest bullish thesis. "
    "Lead with the most compelling metrics. Acknowledge but rebut key risks. "
    "Respond ONLY with a valid JSON object — no markdown."
)

_USER_TEMPLATE = """
Build the bull case for {symbol}.

Analyst reports:
{reports}

{prior_bear}

Return JSON with these exact keys:
{{
  "thesis": "1-2 sentence core bull thesis",
  "supporting_points": ["point 1", "point 2", "point 3"],
  "key_risk_acknowledged": "the most important bear risk and your rebuttal",
  "confidence": "LOW" | "MEDIUM" | "HIGH"
}}
"""


async def run(
    symbol: str,
    reports: list[AnalystReport],
    provider: str,
    model: str | None,
    prior_bear: ResearchCase | None = None,
) -> ResearchCase:
    reports_text = json.dumps([r.model_dump() for r in reports], indent=2)
    bear_section = ""
    if prior_bear:
        bear_section = f"\nBear case to rebut:\n{json.dumps(prior_bear.model_dump(), indent=2)}\n"

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        reports=reports_text,
        prior_bear=bear_section,
    )

    try:
        text = await complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    return ResearchCase(
        side="bull",
        symbol=symbol,
        thesis=parsed.get("thesis", "Bullish on " + symbol),
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
    """Produce a rebuttal bull case given the bear's response."""
    return await run(current.symbol, [], provider, model, prior_bear=opponent)
