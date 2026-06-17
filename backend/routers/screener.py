"""
Stock screener endpoint.

Applies value-investing filters (Buffett/Brealey/Shiller/Munger) to a watchlist.
Data source: FMP /stable/ratios + /stable/profile first, yfinance as fallback.
Enriches passing stocks with ARK research theses and per-ratio financial insights.
Persists every run + per-ticker results to quant.db for AI copilot reference.
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import ScreenerRun, ScreenerResult
from backend.services.knowledge_base import search_theses

router = APIRouter(prefix="/api/screener", tags=["screener"])

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

CRITERIA = {
    "debt_equity_max": 0.5,
    "current_ratio_min": 1.5,
    "pb_max": 2.0,
    "roe_min": 10.0,
    "roa_min": 5.0,
    "interest_coverage_min": 4.0,
}

# Per-ratio insight text grounded in Brealey-Myers and Poor Charlie's Almanack
RATIO_INSIGHTS = {
    "low_leverage": (
        "Brealey-Myers: firms with high financial leverage amplify both returns and distress risk. "
        "D/E ≤ 0.5 signals conservative capital structure — Munger calls this a 'moat preserver'."
    ),
    "good_liquidity": (
        "Current ratio ≥ 1.5 means near-term obligations are well-covered. "
        "Brealey-Myers Ch.30: liquidity buffers protect against financial distress when credit markets tighten."
    ),
    "fair_valuation": (
        "P/B ≤ 2.0 is a Buffett-era margin-of-safety heuristic: paying close to book value "
        "limits downside if earnings disappoint. Brealey-Myers: book value anchors intrinsic value estimates."
    ),
    "strong_roe": (
        "ROE ≥ 10% means the company earns meaningfully above the typical equity cost of capital (~8-10%). "
        "Munger: sustained high ROE is the fingerprint of a durable competitive advantage."
    ),
    "strong_roa": (
        "ROA ≥ 5% shows asset productivity independent of leverage. "
        "Brealey-Myers: ROA = (Net Income / Assets) links directly to the DuPont decomposition of value creation."
    ),
    "debt_serviceable": (
        "Interest coverage ≥ 4× means EBIT covers interest with room to spare. "
        "Brealey-Myers Ch.18: coverage below 2× is a warning sign of near-financial-distress territory."
    ),
}


# ── FMP fundamentals ─────────────────────────────────────────────────────────

async def _fmp_fundamentals(session: httpx.AsyncClient, symbol: str) -> dict | None:
    if not FMP_API_KEY:
        return None
    try:
        ratios_resp, profile_resp = await asyncio.gather(
            session.get(f"{FMP_BASE}/ratios", params={"symbol": symbol, "apikey": FMP_API_KEY, "limit": 1}),
            session.get(f"{FMP_BASE}/profile", params={"symbol": symbol, "apikey": FMP_API_KEY}),
        )
        if ratios_resp.status_code != 200 or profile_resp.status_code != 200:
            return None

        ratios_data = ratios_resp.json()
        profile_data = profile_resp.json()

        ratios = ratios_data[0] if isinstance(ratios_data, list) and ratios_data else {}
        profile = profile_data[0] if isinstance(profile_data, list) and profile_data else {}

        if not ratios and not profile:
            return None

        de = ratios.get("debtEquityRatio")
        if de is not None and de > 20:
            de = de / 100.0

        roe = ratios.get("returnOnEquity")
        roa = ratios.get("returnOnAssets")
        if roe is not None and abs(roe) <= 1:
            roe = roe * 100
        if roa is not None and abs(roa) <= 1:
            roa = roa * 100

        gross_margin = ratios.get("grossProfitMargin")
        if gross_margin is not None and abs(gross_margin) <= 1:
            gross_margin = gross_margin * 100

        # Company description: truncate to ~300 chars for UI
        raw_desc = profile.get("description") or ""
        description = raw_desc[:300].rsplit(" ", 1)[0] + "…" if len(raw_desc) > 300 else raw_desc

        return {
            "symbol": symbol,
            "name": profile.get("companyName") or profile.get("name") or symbol,
            "sector": profile.get("sector") or "",
            "industry": profile.get("industry") or "",
            "description": description,
            "ceo": profile.get("ceo") or "",
            "website": profile.get("website") or "",
            "price": profile.get("price"),
            "market_cap": profile.get("mktCap"),
            "pe_ratio": ratios.get("priceEarningsRatio") or profile.get("pe"),
            "pb_ratio": ratios.get("priceToBookRatio") or profile.get("priceToBook"),
            "roe": roe,
            "roa": roa,
            "debt_equity": de,
            "current_ratio": ratios.get("currentRatio"),
            "interest_coverage": ratios.get("interestCoverageRatio"),
            "gross_margin": gross_margin,
            "free_cashflow": None,
            "_source": "fmp",
        }
    except Exception:
        return None


# ── yfinance fallback ─────────────────────────────────────────────────────────

def _yfinance_fundamentals(symbol: str) -> dict | None:
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info or {}
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if not price:
            return None

        de = info.get("debtToEquity")
        if de is not None:
            de = de / 100.0

        raw_desc = info.get("longBusinessSummary") or ""
        description = raw_desc[:300].rsplit(" ", 1)[0] + "…" if len(raw_desc) > 300 else raw_desc

        return {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName") or symbol,
            "sector": info.get("sector") or "",
            "industry": info.get("industry") or "",
            "description": description,
            "ceo": "",
            "website": info.get("website") or "",
            "price": price,
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "roe": (info.get("returnOnEquity") or 0) * 100,
            "roa": (info.get("returnOnAssets") or 0) * 100,
            "debt_equity": de,
            "current_ratio": info.get("currentRatio"),
            "interest_coverage": (
                info.get("ebitda") and info.get("totalDebt")
                and info["ebitda"] / max(info["totalDebt"] * 0.05, 1)
            ) or None,
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
        "low_leverage":     data.get("debt_equity")       is not None and data["debt_equity"]       <= c["debt_equity_max"],
        "good_liquidity":   data.get("current_ratio")     is not None and data["current_ratio"]     >= c["current_ratio_min"],
        "fair_valuation":   data.get("pb_ratio")          is not None and data["pb_ratio"]          <= c["pb_max"],
        "strong_roe":       data.get("roe")               is not None and data["roe"]               >= c["roe_min"],
        "strong_roa":       data.get("roa")               is not None and data["roa"]               >= c["roa_min"],
        "debt_serviceable": data.get("interest_coverage") is not None and data["interest_coverage"] >= c["interest_coverage_min"],
    }
    passed = sum(checks.values())

    # Build per-ratio insights only for criteria the stock meets
    insights = {k: RATIO_INSIGHTS[k] for k, v in checks.items() if v}

    return {
        **data,
        "criteria_passed": passed,
        "criteria_detail": checks,
        "passes_screen": passed >= 4,
        "ratio_insights": insights,
    }


# ── DB persistence ────────────────────────────────────────────────────────────

async def _persist_run(
    db: AsyncSession,
    tickers_input: str,
    min_criteria: int,
    scored: list[dict],
) -> int:
    passed = sum(1 for s in scored if s["passes_screen"])
    run = ScreenerRun(
        tickers=tickers_input,
        min_criteria=min_criteria,
        passed_count=passed,
        total_count=len(scored),
    )
    db.add(run)
    await db.flush()  # get run.id

    for stock in scored:
        fundamentals = {
            k: stock.get(k)
            for k in ("price", "market_cap", "pe_ratio", "pb_ratio", "roe", "roa",
                       "debt_equity", "current_ratio", "interest_coverage", "gross_margin",
                       "free_cashflow", "sector", "industry", "description")
        }
        result = ScreenerResult(
            run_id=run.id,
            symbol=stock["symbol"],
            name=stock.get("name"),
            sector=stock.get("sector"),
            passes_screen=stock["passes_screen"],
            criteria_passed=stock["criteria_passed"],
            fundamentals=fundamentals,
        )
        db.add(result)

    await db.commit()
    return run.id


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/run")
async def run_screener(
    tickers: str = Query(..., description="Comma-separated tickers, e.g. AAPL,MSFT,NVDA"),
    min_criteria: int = Query(4, description="Minimum criteria to pass (1-6)"),
    enrich: bool = Query(True, description="Add ARK theses for passing stocks"),
    db: AsyncSession = Depends(get_db),
):
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

    run_id = await _persist_run(db, tickers, min_criteria, scored)

    if enrich:
        for stock in scored:
            if stock["criteria_passed"] < min_criteria:
                continue
            stock["theses"] = await search_theses(entity=stock["symbol"], theme=None, limit=5, db=db)

    return {"results": scored, "criteria": CRITERIA, "run_id": run_id}


@router.get("/history")
async def screener_history(
    limit: int = Query(20, description="Most recent N runs"),
    db: AsyncSession = Depends(get_db),
):
    """Return recent screener runs with their per-ticker results (for AI copilot tool use)."""
    stmt = (
        select(ScreenerRun)
        .order_by(desc(ScreenerRun.ran_at))
        .limit(limit)
    )
    result = await db.execute(stmt)
    runs = result.scalars().all()

    output = []
    for run in runs:
        results_stmt = select(ScreenerResult).where(ScreenerResult.run_id == run.id)
        res = await db.execute(results_stmt)
        items = res.scalars().all()
        output.append({
            "run_id": run.id,
            "ran_at": run.ran_at.isoformat(),
            "tickers": run.tickers,
            "min_criteria": run.min_criteria,
            "passed_count": run.passed_count,
            "total_count": run.total_count,
            "results": [
                {
                    "symbol": r.symbol,
                    "name": r.name,
                    "sector": r.sector,
                    "passes_screen": r.passes_screen,
                    "criteria_passed": r.criteria_passed,
                    "fundamentals": r.fundamentals,
                }
                for r in items
            ],
        })
    return {"runs": output}


@router.get("/models")
async def list_ollama_models():
    from backend.services.ollama_client import OLLAMA_HOST
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{OLLAMA_HOST}/api/tags")
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            return {"models": models, "available": True}
    except Exception:
        return {"models": [], "available": False}
