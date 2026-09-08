"""
Data adapter — wraps FMP and Yahoo behind a provider-agnostic daily-bar interface.

Declares capabilities explicitly. A caller that requests total_return or ADV-aware
costs must check get_capability() first; this adapter does NOT silently fall back.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import TypedDict

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class BarRecord(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class DailyBarCapability(BaseModel):
    """Declares what this adapter can reliably serve."""
    daily_ohlcv: bool = True
    adjusted_ohlcv_for_total_return: bool = False   # FMP/Yahoo adjusted_close not verified for fills
    corporate_action_events: bool = False
    daily_volume: bool = True
    adv_lookback_coverage: bool = True              # volume present — ADV can be computed
    # total_return requires a verified adjusted series; currently declared False
    total_return_verified: bool = False


def get_capability() -> DailyBarCapability:
    fmp_key = os.getenv("FMP_API_KEY", "")
    return DailyBarCapability(
        daily_ohlcv=True,
        adjusted_ohlcv_for_total_return=False,   # not verified for Phase 2
        corporate_action_events=False,
        daily_volume=True,
        adv_lookback_coverage=True,
        total_return_verified=False,
    )


async def fetch_bars(symbol: str, start_date: str, end_date: str) -> list[BarRecord]:
    """
    Fetch daily OHLCV for one symbol. Tries FMP first, falls back to Yahoo.
    Returns an empty list on failure (caller handles).

    Both providers expose async ``get_history`` coroutines, so they are awaited
    directly. Failures are logged (not swallowed silently) so a genuine
    provider/quota/network problem is diagnosable instead of surfacing only as an
    opaque "no data" downstream.
    """
    from backend.services import fmp as fmp_service
    from backend.services import yahoo as yahoo_service

    try:
        raw = await fmp_service.get_history(symbol, start_date, end_date)
        if raw:
            return _normalize_bars(raw, "fmp")
    except Exception as exc:
        logger.warning("FMP get_history failed for %s (%s→%s): %s", symbol, start_date, end_date, exc)

    try:
        raw = await yahoo_service.get_history(symbol, start_date, end_date)
        if raw:
            return _normalize_bars(raw, "yahoo")
    except Exception as exc:
        logger.warning("Yahoo get_history failed for %s (%s→%s): %s", symbol, start_date, end_date, exc)

    logger.info("No bars returned for %s from FMP or Yahoo (%s→%s)", symbol, start_date, end_date)
    return []


async def fetch_bars_multi(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, list[BarRecord]]:
    """Parallel fetch for all symbols. Returns {symbol: bars}."""
    tasks = {sym: fetch_bars(sym, start_date, end_date) for sym in symbols}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out: dict[str, list[BarRecord]] = {}
    for sym, res in zip(tasks.keys(), results):
        out[sym] = res if isinstance(res, list) else []
    return out


def _normalize_bars(raw: list[dict], source: str) -> list[BarRecord]:
    """Normalize FMP/Yahoo bar dicts to a consistent BarRecord schema."""
    bars: list[BarRecord] = []
    for row in raw:
        try:
            bars.append(BarRecord(
                date=str(row.get("date", row.get("Date", ""))),
                open=float(row.get("open", row.get("Open", 0))),
                high=float(row.get("high", row.get("High", 0))),
                low=float(row.get("low", row.get("Low", 0))),
                close=float(row.get("close", row.get("Close", row.get("adjClose", 0)))),
                volume=int(row.get("volume", row.get("Volume", 0))),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    # Sort ascending by date
    bars.sort(key=lambda b: b["date"])
    return bars


def build_snapshot_manifest(
    bars_by_symbol: dict[str, list[BarRecord]],
    symbols: list[str],
    start_date: str,
    end_date: str,
    source: str,
) -> dict:
    """Build snapshot manifest for DataSnapshot.manifest_json."""
    per_symbol: dict = {}
    total_rows = 0
    for sym in symbols:
        bars = bars_by_symbol.get(sym, [])
        dates = [b["date"] for b in bars]
        row_count = len(bars)
        total_rows += row_count
        if dates:
            # Detect gaps: count missing trading days (rough heuristic)
            expected = (row_count > 0)
            per_symbol[sym] = {
                "first_date": dates[0],
                "last_date": dates[-1],
                "row_count": row_count,
                "has_data": True,
            }
        else:
            per_symbol[sym] = {
                "first_date": None,
                "last_date": None,
                "row_count": 0,
                "has_data": False,
            }

    manifest = {
        "symbols": symbols,
        "requested_start": start_date,
        "requested_end": end_date,
        "source": source,
        "total_rows": total_rows,
        "per_symbol": per_symbol,
    }
    return manifest


def content_hash(bars_by_symbol: dict[str, list[BarRecord]]) -> str:
    """Stable hash of all bar data — used to detect source data changes."""
    canonical = json.dumps(
        {sym: bars for sym, bars in sorted(bars_by_symbol.items())},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:24]
