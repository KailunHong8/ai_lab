"""
FMP API client using the current /stable/ base URL.
Docs: https://site.financialmodelingprep.com/developer/docs
"""
import os
import threading

import httpx
from cachetools import TTLCache
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

# TTL caches — shared across all requests
_quote_cache:   TTLCache = TTLCache(maxsize=200, ttl=30)    # 30s — prices change frequently
_profile_cache: TTLCache = TTLCache(maxsize=200, ttl=3600)  # 1hr — company info is stable
_search_cache:  TTLCache = TTLCache(maxsize=500, ttl=300)   # 5min — search results
_history_cache: TTLCache = TTLCache(maxsize=100, ttl=3600)  # 1hr — EOD data is stable
_cache_lock = threading.Lock()


def _params(**kwargs) -> dict:
    """Merge caller kwargs with the mandatory apikey."""
    return {"apikey": FMP_API_KEY, **kwargs}


def _handle_fmp_error(resp: httpx.Response, context: str) -> None:
    """Raise a descriptive exception for non-2xx FMP responses."""
    code = resp.status_code
    if code == 401:
        raise PermissionError(
            f"FMP API key invalid or missing ({context}). "
            "Check FMP_API_KEY in .env — get a free key at financialmodelingprep.com."
        )
    if code == 402:
        raise PermissionError(
            f"FMP free tier does not cover this data ({context}). "
            "This symbol may be an option, derivative, or international listing. "
            "Yahoo Finance will be used as fallback if available."
        )
    if code == 403:
        raise PermissionError(
            f"FMP access forbidden ({context}). "
            "Your IP may be rate-limited or the API key may be blocked. "
            "Verify your key at financialmodelingprep.com."
        )
    if code == 429:
        raise RuntimeError(
            f"FMP rate limit exceeded ({context}). "
            "The free tier allows ~250-750 requests/day. Wait until tomorrow or upgrade your plan."
        )
    if code == 404:
        raise LookupError(
            f"Symbol or endpoint not found on FMP ({context}). "
            "Verify the ticker is correct and listed on a supported exchange."
        )
    if code >= 500:
        raise RuntimeError(
            f"FMP server error {code} ({context}). This is a FMP outage — try again in a few minutes."
        )
    resp.raise_for_status()


async def get_quote(symbol: str) -> dict:
    """
    Stock Quotes API - Retrieve latest stock prices, volume, and price changes.
    Returns real-time market data including price, change, changesPercentage,
    dayHigh, dayLow, volume, marketCap, etc. Falls back to Yahoo Finance on
    FMP free-tier restrictions.
    """
    key = symbol.upper()
    with _cache_lock:
        if key in _quote_cache:
            return _quote_cache[key]

    result: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{FMP_BASE}/quote", params=_params(symbol=key))
            _handle_fmp_error(resp, "quote")
            data = resp.json()
            result = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
    except (PermissionError, LookupError, httpx.RequestError):
        pass

    if not result:
        from backend.services import yahoo  # late import avoids circular
        result = await yahoo.get_quote(key)

    if result:
        with _cache_lock:
            _quote_cache[key] = result
    return result


async def get_profile(symbol: str) -> dict:
    """
    Company Profile Data API - Get detailed company information including market cap,
    sector, industry, CEO, description, address, website, and current stock price.
    Falls back to Yahoo Finance on FMP free-tier restrictions.
    """
    key = symbol.upper()
    with _cache_lock:
        if key in _profile_cache:
            return _profile_cache[key]

    result: dict = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{FMP_BASE}/profile", params=_params(symbol=key))
            _handle_fmp_error(resp, "profile")
            data = resp.json()
            result = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else {})
    except (PermissionError, LookupError, httpx.RequestError):
        pass

    if not result:
        from backend.services import yahoo
        result = await yahoo.get_profile(key)

    if result:
        with _cache_lock:
            _profile_cache[key] = result
    return result


async def search_symbol(query: str, limit: int = 10) -> list[dict]:
    """
    Company Name Search API - Search for companies by name to find stock symbols.
    Returns [] on error or no matches. Does not fall back to Yahoo (no search API).
    """
    cache_key = (query.lower(), limit)
    with _cache_lock:
        if cache_key in _search_cache:
            return _search_cache[cache_key]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{FMP_BASE}/search-name",
                params=_params(query=query, limit=limit),
            )
            _handle_fmp_error(resp, "search")
            data = resp.json()
            results = data if isinstance(data, list) else []
        with _cache_lock:
            _search_cache[cache_key] = results
        return results
    except (PermissionError, LookupError, RuntimeError, httpx.RequestError):
        return []


async def get_history(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """
    Historical Price Data API - Get end-of-day OHLCV data for backtesting.
    Sorted oldest-first. Falls back to Yahoo Finance on FMP free-tier restrictions.
    Returns [] on unrecoverable error.
    """
    key = (symbol.upper(), from_date, to_date)
    with _cache_lock:
        if key in _history_cache:
            return _history_cache[key]

    result: list = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{FMP_BASE}/historical-price-eod/full",
                params=_params(symbol=symbol.upper(), **{"from": from_date, "to": to_date}),
            )
            _handle_fmp_error(resp, "history")
            data = resp.json()
            if isinstance(data, list):
                result = list(reversed(data))
            elif isinstance(data, dict):
                result = list(reversed(data.get("historical", [])))
    except (PermissionError, LookupError, httpx.RequestError):
        pass

    if not result:
        from backend.services import yahoo
        result = await yahoo.get_history(symbol.upper(), from_date, to_date)

    if result:
        with _cache_lock:
            _history_cache[key] = result
    return result
