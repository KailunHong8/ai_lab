"""Technical analyst agent."""
from __future__ import annotations

import json
from datetime import date

from backend.services import llm, market_data
from backend.services.indicators import full_technical
from backend.services.llm import extract_json
from backend.services.types import AnalystReport

_SYSTEM = (
    "You are a technical analyst. Given price and indicator data, interpret trend, "
    "momentum, and key levels. Respond ONLY with a valid JSON object — no markdown."
)

_USER_TEMPLATE = """
Analyze {symbol} technical setup as of {date}.

Indicators (computed from {period} price history):
{data}

Return JSON with these exact keys:
{{
  "trend": "up" | "down" | "sideways",
  "momentum": "strong" | "weak" | "diverging",
  "macd_signal": "bullish_cross" | "bearish_cross" | "bullish" | "bearish" | "neutral",
  "key_levels": {{"support": <float>, "resistance": <float>}},
  "summary": "2-3 sentence technical assessment including whether setup is entry-worthy"
}}
"""


async def run(symbol: str, analysis_date: date, provider: str, model: str | None) -> AnalystReport:
    period = "1y"
    df = await market_data.get_price_history(symbol, period=period)
    snapshot, key_levels = full_technical(df)

    data_summary = {
        "rsi_14": snapshot.rsi,
        "macd_signal": snapshot.macd_signal,
        "price_vs_sma50": snapshot.price_vs_sma50,
        "price_vs_sma200": snapshot.price_vs_sma200,
        "bollinger_position": snapshot.bollinger_position,
        "computed_trend": snapshot.trend,
        "computed_momentum": snapshot.momentum,
        "support_20d": key_levels.get("support_20d"),
        "resistance_20d": key_levels.get("resistance_20d"),
    }

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        date=str(analysis_date),
        period=period,
        data=json.dumps(data_summary, indent=2),
    )

    try:
        text = await llm.complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    return AnalystReport(
        analyst="technical",
        symbol=symbol,
        trend=parsed.get("trend", snapshot.trend),
        momentum=parsed.get("momentum", snapshot.momentum),
        rsi=snapshot.rsi,
        macd_signal=parsed.get("macd_signal", snapshot.macd_signal),
        key_levels=parsed.get("key_levels", key_levels),
        summary=parsed.get("summary", ""),
        data_sources=["yfinance", "pandas_ta"],
    )
