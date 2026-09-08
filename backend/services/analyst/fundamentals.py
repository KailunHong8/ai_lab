"""Fundamentals analyst agent."""
from __future__ import annotations

import json
from datetime import date

from backend.services import llm, market_data
from backend.services.llm import extract_json
from backend.services.types import AnalystReport

_SYSTEM = (
    "You are a fundamental analyst. Given company financial data, assess valuation, "
    "earnings quality, balance sheet health, revenue trajectory, and catalysts. "
    "Respond ONLY with a valid JSON object — no markdown, no explanation."
)

_USER_TEMPLATE = """
Analyze {symbol} fundamentals as of {date}.

Data:
{data}

Return JSON with these exact keys:
{{
  "valuation_signal": "cheap" | "fair" | "expensive",
  "quality_signal": "strong" | "neutral" | "weak",
  "catalyst": "one sentence on the most important near-term catalyst",
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "summary": "2-3 sentence fundamental assessment"
}}
"""


async def run(symbol: str, analysis_date: date, provider: str, model: str | None) -> AnalystReport:
    fundamentals = await market_data.get_fundamentals(symbol)
    profile = await market_data.get_profile(symbol)

    data_summary = {
        "name": profile.name,
        "sector": profile.sector,
        "pe_ratio": fundamentals.pe_ratio,
        "eps": fundamentals.eps,
        "revenue_ttm_bn": round(fundamentals.revenue_ttm / 1e9, 2) if fundamentals.revenue_ttm else None,
        "gross_margin_pct": round(fundamentals.gross_margin * 100, 1) if fundamentals.gross_margin else None,
        "debt_equity": fundamentals.debt_equity,
        "roe_pct": round(fundamentals.roe * 100, 1) if fundamentals.roe else None,
        "next_earnings_date": fundamentals.next_earnings_date,
        "income_trend": fundamentals.income_trend,
    }

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        date=str(analysis_date),
        data=json.dumps(data_summary, indent=2),
    )

    try:
        text = await llm.complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    return AnalystReport(
        analyst="fundamentals",
        symbol=symbol,
        valuation_signal=parsed.get("valuation_signal", "fair"),
        quality_signal=parsed.get("quality_signal", "neutral"),
        catalyst=parsed.get("catalyst"),
        key_risks=parsed.get("key_risks", []),
        summary=parsed.get("summary", ""),
        data_sources=["yfinance"],
    )
