"""Unified market data client — yfinance primary, Finnhub supplement, SQLite cache."""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional

import yfinance as yf

from backend.services.types import (
    Quote, CompanyProfile, Fundamentals, NewsItem, SentimentScore,
)

FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "")

# Cache TTLs in seconds
_TTL = {
    "quote": 60,
    "fundamentals": 86400,
    "history": 3600,
    "news": 7200,
    "sentiment": 14400,
    "profile": 86400,
}


# ── Cache helpers ──────────────────────────────────────────────────────────────

async def _cache_get(key: str) -> Optional[dict]:
    from backend.db import SessionLocal
    from backend.models import DataCache
    from sqlalchemy import select
    async with SessionLocal() as db:
        row = await db.get(DataCache, key)
        if row and row.expires_at > datetime.utcnow():
            return json.loads(row.data)
    return None


async def _cache_set(key: str, data: dict, ttl: int) -> None:
    from backend.db import SessionLocal
    from backend.models import DataCache
    async with SessionLocal() as db:
        expires = datetime.utcnow() + timedelta(seconds=ttl)
        row = await db.get(DataCache, key)
        if row:
            row.data = json.dumps(data)
            row.expires_at = expires
        else:
            db.add(DataCache(key=key, data=json.dumps(data), expires_at=expires))
        await db.commit()


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_quote(symbol: str) -> Quote:
    key = f"quote:{symbol}"
    cached = await _cache_get(key)
    if cached:
        return Quote(**cached)

    def _fetch():
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = float(getattr(info, "last_price", None) or 0)
        market_cap = float(getattr(info, "market_cap", None) or 0) or None
        volume = int(getattr(info, "last_volume", None) or 0) or None
        full = ticker.info
        return {
            "symbol": symbol,
            "name": full.get("shortName", ""),
            "price": price,
            "change_pct": round(float(full.get("regularMarketChangePercent", 0) or 0), 4),
            "volume": volume,
            "market_cap": market_cap,
            "open": float(full.get("regularMarketOpen") or 0) or None,
            "day_high": float(full.get("dayHigh") or 0) or None,
            "day_low": float(full.get("dayLow") or 0) or None,
        }

    data = await asyncio.to_thread(_fetch)
    await _cache_set(key, data, _TTL["quote"])
    return Quote(**data)


async def get_profile(symbol: str) -> CompanyProfile:
    key = f"profile:{symbol}"
    cached = await _cache_get(key)
    if cached:
        return CompanyProfile(**cached)

    def _fetch():
        info = yf.Ticker(symbol).info
        return {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "description": info.get("longBusinessSummary", ""),
        }

    data = await asyncio.to_thread(_fetch)
    await _cache_set(key, data, _TTL["profile"])
    return CompanyProfile(**data)


async def get_fundamentals(symbol: str) -> Fundamentals:
    key = f"fundamentals:{symbol}"
    cached = await _cache_get(key)
    if cached:
        return Fundamentals(**cached)

    def _fetch():
        ticker = yf.Ticker(symbol)
        info = ticker.info
        # Income trend: last 3 years of annual revenue/earnings
        try:
            inc = ticker.income_stmt
            income_trend = {
                str(col.year): {
                    "revenue": float(inc.loc["Total Revenue", col]) if "Total Revenue" in inc.index else None,
                    "net_income": float(inc.loc["Net Income", col]) if "Net Income" in inc.index else None,
                }
                for col in list(inc.columns)[:3]
            } if inc is not None and not inc.empty else None
        except Exception:
            income_trend = None

        try:
            bal = ticker.balance_sheet
            balance_trend = {
                str(col.year): {
                    "total_assets": float(bal.loc["Total Assets", col]) if "Total Assets" in bal.index else None,
                    "total_debt": float(bal.loc["Total Debt", col]) if "Total Debt" in bal.index else None,
                }
                for col in list(bal.columns)[:3]
            } if bal is not None and not bal.empty else None
        except Exception:
            balance_trend = None

        # Earnings calendar
        try:
            cal = ticker.calendar
            next_earnings = None
            if cal is not None and isinstance(cal, dict) and "Earnings Date" in cal:
                dates = cal["Earnings Date"]
                if dates:
                    next_earnings = str(dates[0].date()) if hasattr(dates[0], "date") else str(dates[0])
        except Exception:
            next_earnings = None

        return {
            "symbol": symbol,
            "pe_ratio": info.get("trailingPE"),
            "eps": info.get("trailingEps"),
            "revenue_ttm": info.get("totalRevenue"),
            "gross_margin": info.get("grossMargins"),
            "debt_equity": info.get("debtToEquity"),
            "roe": info.get("returnOnEquity"),
            "earnings_surprise": info.get("earningsSurpriseAvg"),
            "next_earnings_date": next_earnings,
            "income_trend": income_trend,
            "balance_trend": balance_trend,
        }

    data = await asyncio.to_thread(_fetch)
    await _cache_set(key, data, _TTL["fundamentals"])
    return Fundamentals(**data)


async def get_price_history(symbol: str, period: str = "1y"):
    """Returns a pandas DataFrame of OHLCV data."""
    import pandas as pd

    def _fetch():
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, auto_adjust=True)
        return df

    return await asyncio.to_thread(_fetch)


async def get_news(symbol: str, limit: int = 30) -> list[NewsItem]:
    key = f"news:{symbol}"
    cached = await _cache_get(key)
    if cached:
        return [NewsItem(**n) for n in cached]

    items: list[dict] = []

    # yfinance news
    def _yf_news():
        ticker = yf.Ticker(symbol)
        news = ticker.news or []
        result = []
        for n in news[:limit]:
            content = n.get("content", {})
            result.append({
                "headline": content.get("title", "") or n.get("title", ""),
                "summary": content.get("summary", "") or "",
                "url": (content.get("canonicalUrl", {}) or {}).get("url", "") or "",
                "source": (content.get("provider", {}) or {}).get("displayName", "") or "",
                "published_at": content.get("pubDate", "") or "",
            })
        return result

    items = await asyncio.to_thread(_yf_news)

    # Finnhub supplement
    if FINNHUB_KEY and len(items) < limit:
        try:
            import finnhub
            fh = finnhub.Client(api_key=FINNHUB_KEY)
            from datetime import date, timedelta
            today = date.today()
            week_ago = today - timedelta(days=7)

            def _fh_news():
                return fh.company_news(symbol, _from=str(week_ago), to=str(today))

            fh_news = await asyncio.to_thread(_fh_news)
            seen = {i["headline"] for i in items}
            for n in (fh_news or [])[:limit]:
                headline = n.get("headline", "")
                if headline and headline not in seen:
                    items.append({
                        "headline": headline,
                        "summary": n.get("summary", ""),
                        "url": n.get("url", ""),
                        "source": n.get("source", ""),
                        "published_at": str(n.get("datetime", "")),
                    })
                    seen.add(headline)
        except Exception:
            pass

    items = items[:limit]
    await _cache_set(key, items, _TTL["news"])
    return [NewsItem(**n) for n in items]


async def get_news_sentiment(symbol: str) -> Optional[SentimentScore]:
    if not FINNHUB_KEY:
        return None

    key = f"sentiment:{symbol}"
    cached = await _cache_get(key)
    if cached:
        return SentimentScore(**cached)

    try:
        import finnhub
        fh = finnhub.Client(api_key=FINNHUB_KEY)

        def _fetch():
            return fh.news_sentiment(symbol)

        data = await asyncio.to_thread(_fetch)
        if not data or "sentiment" not in data:
            return None

        s = data["sentiment"]
        result = {
            "bullish_pct": float(s.get("bullishPercent", 0)),
            "bearish_pct": float(s.get("bearishPercent", 0)),
            "score": float(data.get("companyNewsScore", 0)),
            "article_count": int(data.get("articlesInLastWeek", 0)),
        }
        await _cache_set(key, result, _TTL["sentiment"])
        return SentimentScore(**result)
    except Exception:
        return None
