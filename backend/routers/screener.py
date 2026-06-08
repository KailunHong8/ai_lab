"""
Stock screener endpoint.

Applies value-investing filters (Buffett/Brealey/Shiller/Munger) to a watchlist.
Data source: FMP /stable/ratios first, yfinance as fallback.
Enriches passing stocks with ARK research theses and investing principles.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.services.knowledge_base import search_theses
from backend.services.research import search_principles

router = APIRouter(prefix="/api/screener", tags=["screener"])

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

# Criteria (Buffett / Brealey-Myers / Munger)
CRITERIA = {
    "debt_equity_max": 0.5,
    "current_ratio_min": 1.5,
    "pb_max": 2.0,
    "roe_min": 10.0,
    "roa_min": 5.0,
    "interest_coverage_min": 4.0,
}

PRINCIPLES_QUERY = "value investing criteria ROE ROA debt equity margin of safety quality compounder"


# ── FMP fundamentals ─────────────────────────────────────────────────────────

async def _fmp_fundamentals(session: httpx.AsyncClient, symbol: str) -> dict | None:
    """Fetch key ratios + profile from FMP. Returns None on any error."""
    if not FMP_API_KEY:
        return None
    try:
        ratios_resp, profile_resp = await asyncio.gather(
            session.get(f"{FMP_BASE}/ratios", params={"symbol": symbol, "apikey": FMP_API_KEY, "limit": 1}),
            session.get(f"{FMP_BASE}/profile", params={"symbol": symbol, "apikey": FMP_API_KEY}),
        )
        if ratios_resp.status_code not in (200,) or profile_resp.status_code not in (200,):
            return None

        ratios_data = ratios_resp.json()
        profile_data = profile_resp.json()

        ratios = ratios_data[0] if isinstance(ratios_data, list) and ratios_data else {}
        profile = profile_data[0] if isinstance(profile_data, list) and profile_data else {}

        if not ratios and not profile:
            return None

        de = ratios.get("debtEquityRatio")
        # Some FMP responses express D/E as-is (not ×100); keep as-is
        if de is not None and de > 20:
            de = de / 100.0  # guard: some endpoints return percent

        roe = ratios.get("returnOnEquity")
        roa = ratios.get("returnOnAssets")
        if roe is not None and abs(roe) <= 1:
            roe = roe * 100
        if roa is not None and abs(roa) <= 1:
            roa = roa * 100

        return {
            "symbol": symbol,
            "name": profile.get("companyName") or profile.get("name") or symbol,
            "sector": profile.get("sector") or "",
            "price": profile.get("price"),
            "market_cap": profile.get("mktCap"),
            "pe_ratio": ratios.get("priceEarningsRatio") or profile.get("pe"),
            "pb_ratio": ratios.get("priceToBookRatio") or profile.get("priceToBook"),
            "roe": roe,
            "roa": roa,
            "debt_equity": de,
            "current_ratio": ratios.get("currentRatio"),
            "interest_coverage": ratios.get("interestCoverageRatio"),
            "gross_margin": (ratios.get("grossProfitMargin") or 0) * 100 if ratios.get("grossProfitMargin") and abs(ratios.get("grossProfitMargin")) <= 1 else ratios.get("grossProfitMargin"),
            "free_cashflow": None,
            "_source": "fmp",
        }
    except Exception:
        return None


# ── yfinance fallback ─────────────────────────────────────────────────────────

def _yfinance_fundamentals(symbol: str) -> dict | None:
    """Blocking yfinance call — run via asyncio.to_thread."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None

        de = info.get("debtToEquity")
        if de is not None:
            de = de / 100.0

        roe = (info.get("returnOnEquity") or 0) * 100
        roa = (info.get("returnOnAssets") or 0) * 100

        return {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName") or symbol,
            "sector": info.get("sector") or "",
            "price": price,
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": roe,
            "roa": roa,
            "debt_equity": de,
            "current_ratio": info.get("currentRatio"),
            "interest_coverage": info.get("ebitda") and info.get("totalDebt")
                and info["ebitda"] / max(info["totalDebt"] * 0.05, 1)
                or None,
            "gross_margin": (info.get("grossMargins") or 0) * 100,
            "free_cashflow": info.get("freeCashflow"),
            "_source": "yfinance",
        }
    except Exception:
        return None


# ── scoring ───────────────────────────────────────────────────────────────────

def _score(data: dict) -> dict:
    c = CRITERIA
    checks = {
        "low_leverage":    data.get("debt_equity")       is not None and data["debt_equity"]       <= c["debt_equity_max"],
        "good_liquidity":  data.get("current_ratio")     is not None and data["current_ratio"]     >= c["current_ratio_min"],
        "fair_valuation":  data.get("pb_ratio")          is not None and data["pb_ratio"]          <= c["pb_max"],
        "strong_roe":      data.get("roe")               is not None and data["roe"]               >= c["roe_min"],
        "strong_roa":      data.get("roa")               is not None and data["roa"]               >= c["roa_min"],
        "debt_serviceable": data.get("interest_coverage") is not None and data["interest_coverage"] >= c["interest_coverage_min"],
    }
    passed = sum(checks.values())
    return {**data, "criteria_passed": passed, "criteria_detail": checks, "passes_screen": passed >= 4}


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/run")
async def run_screener(
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT,NVDA"),
    min_criteria: int = Query(4, description="Minimum criteria to pass (1-6)"),
    enrich: bool = Query(True, description="Add ARK theses and principles for passing stocks"),
    db: AsyncSession = Depends(get_db),
):
    """
    Value screen a watchlist. FMP fundamentals first, yfinance on failure.
    Returns all tickers scored + enrichment for passing stocks.
    """
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        return {"results": [], "criteria": CRITERIA}

    semaphore = asyncio.Semaphore(6)

    async def _fetch(sym: str) -> dict | None:
        async with semaphore:
            async with httpx.AsyncClient(timeout=12.0) as session:
                data = await _fmp_fundamentals(session, sym)
            if data is None:
                data = await asyncio.to_thread(_yfinance_fundamentals, sym)
            return data

    raw = await asyncio.gather(*[_fetch(s) for s in symbols])
    scored = sorted(
        [_score(d) for d in raw if d is not None],
        key=lambda x: x["criteria_passed"],
        reverse=True,
    )

    if not enrich:
        return {"results": scored, "criteria": CRITERIA}

    principles = search_principles(PRINCIPLES_QUERY, top_k=1)
    principles_snippet = principles[0]["text"][:500] if principles else ""

    for stock in scored:
        if stock["criteria_passed"] < min_criteria:
            continue
        stock["theses"] = await search_theses(entity=stock["symbol"], theme=None, limit=5, db=db)
        stock["principles_note"] = principles_snippet

    return {"results": scored, "criteria": CRITERIA}


@router.get("/models")
async def list_ollama_models():
    """List locally available Ollama models (for provider selector UI)."""
    from backend.services.ollama_client import OLLAMA_HOST
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models, "available": True}
    except Exception:
        return {"models": [], "available": False}
