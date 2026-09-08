"""Sentiment and news analyst agent."""
from __future__ import annotations

import json
from datetime import date

from backend.services import llm, market_data
from backend.services.fred import get_macro_snapshot
from backend.services.llm import extract_json
from backend.services.types import AnalystReport

_SYSTEM = (
    "You are a market sentiment analyst. Given recent news, sentiment scores, and macro data, "
    "assess the news tone, dominant themes, and macro headwinds/tailwinds. "
    "Respond ONLY with a valid JSON object — no markdown."
)

_USER_TEMPLATE = """
Analyze {symbol} sentiment as of {date}.

Recent news ({news_count} articles):
{headlines}

Sentiment score (Finnhub): {sentiment}

Macroeconomic context:
{macro}

Return JSON with these exact keys:
{{
  "news_tone": "positive" | "neutral" | "negative",
  "top_themes": ["theme 1", "theme 2", "theme 3"],
  "sentiment_score": <float -1.0 to 1.0>,
  "macro_context": "1-2 sentences on macro headwinds/tailwinds",
  "summary": "2-3 sentence sentiment assessment"
}}
"""


async def run(symbol: str, analysis_date: date, provider: str, model: str | None) -> AnalystReport:
    news, sentiment, macro = await _gather(symbol)

    headlines = "\n".join(
        f"- [{n.published_at[:10] if n.published_at else ''}] {n.headline}"
        for n in news[:15]
    )
    sentiment_str = (
        f"bullish {sentiment.bullish_pct:.0f}% / bearish {sentiment.bearish_pct:.0f}%, "
        f"score {sentiment.score:.2f}, {sentiment.article_count} articles"
        if sentiment else "unavailable"
    )
    macro_str = json.dumps({
        "fed_funds_rate": macro.fed_funds_rate,
        "cpi_yoy": macro.cpi_yoy,
        "yield_curve_10y2y": macro.yield_curve,
        "vix": macro.vix,
        "yield_curve_trend": macro.yield_curve_trend,
        "vix_trend": macro.vix_trend,
    }, indent=2)

    user_msg = _USER_TEMPLATE.format(
        symbol=symbol,
        date=str(analysis_date),
        news_count=len(news),
        headlines=headlines or "(no recent news)",
        sentiment=sentiment_str,
        macro=macro_str,
    )

    try:
        text = await llm.complete(_SYSTEM, user_msg, provider, model)
        parsed = extract_json(text)
    except Exception:
        parsed = {}

    sources = ["yfinance"]
    if sentiment is not None:
        sources.append("finnhub")
    if macro.fed_funds_rate is not None:
        sources.append("fred")

    return AnalystReport(
        analyst="sentiment",
        symbol=symbol,
        news_tone=parsed.get("news_tone", "neutral"),
        top_themes=parsed.get("top_themes", []),
        sentiment_score=parsed.get("sentiment_score"),
        macro_context=parsed.get("macro_context"),
        summary=parsed.get("summary", ""),
        data_sources=sources,
    )


async def _gather(symbol: str):
    import asyncio
    news, sentiment, macro = await asyncio.gather(
        market_data.get_news(symbol, limit=30),
        market_data.get_news_sentiment(symbol),
        get_macro_snapshot(),
    )
    return news, sentiment, macro
