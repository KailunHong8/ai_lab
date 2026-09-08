"""FRED macroeconomic data client with SQLite cache."""
from __future__ import annotations

import asyncio
import os
from typing import Optional

from backend.services.types import MacroSnapshot

FRED_KEY = os.getenv("FRED_API_KEY", "")

MACRO_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi_yoy": "CPIAUCSL",
    "unemployment": "UNRATE",
    "yield_curve": "T10Y2Y",
    "vix": "VIXCLS",
}

_CACHE_KEY = "macro:snapshot"
_CACHE_TTL = 86400  # 24h


async def get_macro_snapshot() -> MacroSnapshot:
    from backend.services.market_data import _cache_get, _cache_set

    cached = await _cache_get(_CACHE_KEY)
    if cached:
        return MacroSnapshot(**cached)

    if not FRED_KEY:
        return MacroSnapshot()

    def _fetch():
        from fredapi import Fred
        fred = Fred(api_key=FRED_KEY)
        result: dict = {}
        for field, series_id in MACRO_SERIES.items():
            try:
                s = fred.get_series(series_id, observation_start="2000-01-01")
                s = s.dropna()
                if s.empty:
                    continue
                result[field] = float(s.iloc[-1])
                # 3-month trend: compare last value to 3 months ago
                if len(s) >= 3:
                    prev = float(s.iloc[-3])
                    curr = float(s.iloc[-1])
                    diff = curr - prev
                    if abs(diff) < 0.01:
                        trend = 0
                    elif diff > 0:
                        trend = 1
                    else:
                        trend = -1
                    trend_field = field.replace("fed_funds_rate", "fed_funds").replace("cpi_yoy", "cpi") + "_trend"
                    result[trend_field] = trend
            except Exception:
                pass
        return result

    data = await asyncio.to_thread(_fetch)
    await _cache_set(_CACHE_KEY, data, _CACHE_TTL)
    return MacroSnapshot(**{k: v for k, v in data.items() if k in MacroSnapshot.model_fields})
