"""
Yahoo Finance adapter — fallback data source when FMP free tier lacks coverage.
All yfinance calls are synchronous; we wrap them in asyncio.to_thread().
"""
import asyncio

import yfinance as yf


async def get_quote(symbol: str) -> dict:
    """Fetch real-time quote from Yahoo Finance, mapped to FMP field names."""
    def _fetch():
        ticker = yf.Ticker(symbol)
        info = ticker.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return {}
        pct = info.get("regularMarketChangePercent", 0)
        # yfinance returns the value as a fraction (e.g. 0.015), FMP as percent (1.5)
        if isinstance(pct, float) and abs(pct) < 1:
            pct = pct * 100
        return {
            "symbol": symbol,
            "name": info.get("shortName", ""),
            "price": price,
            "changesPercentage": round(pct, 4),
            "open": info.get("open") or info.get("regularMarketOpen"),
            "dayHigh": info.get("dayHigh") or info.get("regularMarketDayHigh"),
            "dayLow": info.get("dayLow") or info.get("regularMarketDayLow"),
            "volume": info.get("volume") or info.get("regularMarketVolume"),
            "marketCap": info.get("marketCap"),
            "_source": "yahoo",
        }
    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return {}


async def get_profile(symbol: str) -> dict:
    """Fetch company profile from Yahoo Finance, mapped to FMP field names."""
    def _fetch():
        ticker = yf.Ticker(symbol)
        info = ticker.info
        if not info.get("shortName"):
            return {}
        return {
            "symbol": symbol,
            "companyName": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "description": info.get("longBusinessSummary", ""),
            "website": info.get("website", ""),
            "ceo": info.get("companyOfficers", [{}])[0].get("name", "") if info.get("companyOfficers") else "",
            "mktCap": info.get("marketCap"),
            "country": info.get("country", ""),
            "_source": "yahoo",
        }
    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return {}


async def get_history(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """Fetch EOD OHLCV history from Yahoo Finance, sorted oldest-first."""
    def _fetch():
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=from_date, end=to_date)
        if df.empty:
            return []
        records = []
        for ts, row in df.iterrows():
            records.append({
                "date": ts.strftime("%Y-%m-%d"),
                "open": round(float(row["Open"]), 4),
                "high": round(float(row["High"]), 4),
                "low": round(float(row["Low"]), 4),
                "close": round(float(row["Close"]), 4),
                "volume": int(row["Volume"]),
                "_source": "yahoo",
            })
        return records  # yfinance returns oldest-first by default
    try:
        return await asyncio.to_thread(_fetch)
    except Exception:
        return []


async def search_symbol(query: str, limit: int = 10) -> list[dict]:
    """Yahoo Finance has no public search API; static frontend tickers cover this."""
    return []
