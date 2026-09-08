"""
Strategy Studio REST API — /api/strategies

Endpoints:
  POST   /api/strategies/parse              parse description → StrategyDefinition draft
  POST   /api/strategies                    create strategy + initial draft version
  GET    /api/strategies                    list strategies
  GET    /api/strategies/{id}               get strategy + all versions
  PUT    /api/strategies/{id}/versions/{vid} update a draft version (immutable once promoted)
  POST   /api/strategies/{id}/versions/{vid}/promote  promote draft → reviewed
  GET    /api/strategies/{id}/versions/{vid}/compile  static validation
  POST   /api/strategies/{id}/versions/{vid}/validate rolling validation run
  POST   /api/strategies/{id}/versions/{vid}/backtest backtest run (persists SimulationRun)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import (
    Strategy,
    StrategyVersion,
    DataSnapshot,
    ValidationReport,
    SimulationRun,
)
from backend.services.strategy.schema import StrategyDefinition, DataSpec
from backend.services.strategy.compiler import compile_strategy, FindingSeverity
from backend.services.strategy.parser_adapter import legacy_to_strategy_definition
from backend.services.strategy.data_adapter import (
    fetch_bars_multi,
    build_snapshot_manifest,
    content_hash,
    get_capability,
)
from backend.services.strategy.engine import run_single, run_portfolio
from backend.services.strategy.validation_protocol import run_rolling_folds
from backend.services.strategy.metrics import compute_all

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


# ── Request models ─────────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    strategy_description: str
    start_date: str
    end_date: str
    benchmark: str = "SPY"
    provider: str = "bedrock"
    model: Optional[str] = None
    commission_bps: float = 2.0
    slippage_bps: float = 5.0


class CreateStrategyRequest(BaseModel):
    name: str
    description: Optional[str] = None
    definition: dict
    source_prompt: Optional[str] = None
    parser_output_json: Optional[str] = None


class UpdateVersionRequest(BaseModel):
    definition: dict
    user_edits_note: Optional[str] = None


class ValidateRequest(BaseModel):
    n_folds: int = 5
    holdout_pct: float = 0.20
    bootstrap_sims: int = 300


class BacktestRequest(BaseModel):
    initial_capital: float = 10000.0
    benchmark_symbol: str = "SPY"
    run_monte_carlo: bool = True
    monte_carlo_sims: int = 300


# ── Helpers ────────────────────────────────────────────────────────────────────

def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


def _load_definition(version: StrategyVersion) -> StrategyDefinition:
    try:
        return StrategyDefinition.model_validate(json.loads(version.definition_json))
    except Exception as exc:
        raise HTTPException(400, f"Strategy definition is invalid: {exc}")


def _version_summary(v: StrategyVersion) -> dict:
    return {
        "id": v.id,
        "version_number": v.version_number,
        "status": v.status,
        "definition_hash": v.definition_hash,
        "schema_version": v.schema_version,
        "reviewed_at": v.reviewed_at.isoformat() if v.reviewed_at else None,
        "created_at": v.created_at.isoformat(),
    }


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/parse")
async def parse_to_definition(req: ParseRequest) -> dict:
    """
    Parse a natural-language description → StrategyDefinition draft.
    No DB write — caller must call POST /api/strategies to persist.
    """
    from backend.routers.simulation import _parse_strategy_dual

    try:
        parsed = await _parse_strategy_dual(req.strategy_description, req.provider, req.model)
    except Exception as exc:
        raise HTTPException(502, f"LLM parse failed: {exc}")

    defn = legacy_to_strategy_definition(
        parsed,
        start_date=req.start_date,
        end_date=req.end_date,
        benchmark=req.benchmark,
        commission_bps=req.commission_bps,
        slippage_bps=req.slippage_bps,
    )
    plan = compile_strategy(defn)

    return {
        "definition": defn.model_dump(),
        "definition_hash": defn.definition_hash(),
        "findings": plan.findings,
        "is_runnable": plan.is_runnable,
        "warmup_bars": plan.warmup_bars,
        "parse_warnings": parsed.get("parse_warnings", []),
        "parser_output": json.dumps(parsed),
    }


@router.post("")
async def create_strategy(req: CreateStrategyRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Create a new strategy with an initial draft version."""
    # Validate definition
    try:
        defn = StrategyDefinition.model_validate(req.definition)
    except Exception as exc:
        raise HTTPException(422, f"Invalid strategy definition: {exc}")

    strategy_id = _new_id()
    version_id = _new_id()
    now = _now()

    strategy = Strategy(
        id=strategy_id,
        name=req.name,
        description=req.description,
        created_at=now,
        updated_at=now,
    )
    db.add(strategy)

    plan = compile_strategy(defn)
    version = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version_number=1,
        definition_json=defn.model_dump_json(),
        definition_hash=defn.definition_hash(),
        status="draft",
        source_prompt=req.source_prompt,
        parser_output_json=req.parser_output_json,
        compiled_plan_json=json.dumps({"findings": plan.findings, "is_runnable": plan.is_runnable, "warmup_bars": plan.warmup_bars}),
        schema_version=1,
        created_at=now,
    )
    db.add(version)
    await db.commit()

    return {
        "strategy_id": strategy_id,
        "version_id": version_id,
        "version_number": 1,
        "definition_hash": defn.definition_hash(),
        "is_runnable": plan.is_runnable,
        "findings": plan.findings,
    }


@router.get("")
async def list_strategies(db: AsyncSession = Depends(get_db)) -> list:
    result = await db.execute(
        select(Strategy).where(Strategy.archived_at == None).order_by(Strategy.created_at.desc())  # noqa: E711
    )
    strategies = result.scalars().all()
    out = []
    for s in strategies:
        vq = await db.execute(
            select(StrategyVersion)
            .where(StrategyVersion.strategy_id == s.id)
            .order_by(StrategyVersion.version_number.desc())
        )
        versions = vq.scalars().all()
        latest = versions[0] if versions else None
        out.append({
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "created_at": s.created_at.isoformat(),
            "version_count": len(versions),
            "latest_version_number": latest.version_number if latest else 0,
            "latest_status": latest.status if latest else None,
            "latest_definition_hash": latest.definition_hash if latest else None,
        })
    return out


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    strategy = await db.get(Strategy, strategy_id)
    if not strategy:
        raise HTTPException(404, "Strategy not found")

    vq = await db.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.asc())
    )
    versions = vq.scalars().all()

    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "created_at": strategy.created_at.isoformat(),
        "versions": [_version_summary(v) for v in versions],
        "latest_definition": json.loads(versions[-1].definition_json) if versions else None,
    }


@router.put("/{strategy_id}/versions/{version_id}")
async def update_version(
    strategy_id: str,
    version_id: str,
    req: UpdateVersionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a draft version. Immutable once status != 'draft'."""
    version = await db.get(StrategyVersion, version_id)
    if not version or version.strategy_id != strategy_id:
        raise HTTPException(404, "Version not found")
    if version.status != "draft":
        raise HTTPException(409, "Version is immutable after promotion. Create a new version instead.")

    try:
        defn = StrategyDefinition.model_validate(req.definition)
    except Exception as exc:
        raise HTTPException(422, f"Invalid definition: {exc}")

    plan = compile_strategy(defn)
    version.definition_json = defn.model_dump_json()
    version.definition_hash = defn.definition_hash()
    version.user_edits_json = json.dumps({"note": req.user_edits_note}) if req.user_edits_note else None
    version.compiled_plan_json = json.dumps({
        "findings": plan.findings,
        "is_runnable": plan.is_runnable,
        "warmup_bars": plan.warmup_bars,
    })
    await db.commit()

    return {
        "version_id": version_id,
        "definition_hash": version.definition_hash,
        "is_runnable": plan.is_runnable,
        "findings": plan.findings,
    }


@router.post("/{strategy_id}/versions/{version_id}/promote")
async def promote_version(
    strategy_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Promote a draft to 'reviewed'. Irreversible."""
    version = await db.get(StrategyVersion, version_id)
    if not version or version.strategy_id != strategy_id:
        raise HTTPException(404, "Version not found")
    if version.status != "draft":
        raise HTTPException(409, f"Version is already '{version.status}'.")

    # Must be runnable before promotion
    defn = _load_definition(version)
    plan = compile_strategy(defn)
    if not plan.is_runnable:
        errors = [f for f in plan.findings if f.get("severity") == "error"]
        raise HTTPException(422, {
            "message": "Cannot promote a version with blocking errors.",
            "errors": errors,
        })

    version.status = "reviewed"
    version.reviewed_at = _now()
    await db.commit()

    return {"version_id": version_id, "status": "reviewed", "reviewed_at": version.reviewed_at.isoformat()}


@router.get("/{strategy_id}/versions/{version_id}/compile")
async def compile_version(
    strategy_id: str,
    version_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Static validation — no DB write, no data fetch."""
    version = await db.get(StrategyVersion, version_id)
    if not version or version.strategy_id != strategy_id:
        raise HTTPException(404, "Version not found")

    defn = _load_definition(version)
    plan = compile_strategy(defn)

    return {
        "version_id": version_id,
        "definition_hash": defn.definition_hash(),
        "is_runnable": plan.is_runnable,
        "warmup_bars": plan.warmup_bars,
        "findings": plan.findings,
    }


@router.post("/{strategy_id}/versions/{version_id}/validate")
async def validate_version(
    strategy_id: str,
    version_id: str,
    req: ValidateRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Run rolling validation (folds + holdout + block bootstrap).
    Fetches data, persists DataSnapshot + ValidationReport.
    """
    version = await db.get(StrategyVersion, version_id)
    if not version or version.strategy_id != strategy_id:
        raise HTTPException(404, "Version not found")

    defn = _load_definition(version)
    plan = compile_strategy(defn)
    if not plan.is_runnable:
        raise HTTPException(422, {
            "message": "Version has blocking validation errors.",
            "findings": plan.findings,
        })

    # Check total_return capability
    cap = get_capability()
    if defn.data.price_basis == "total_return" and not cap.total_return_verified:
        raise HTTPException(422, "total_return is not supported by the current data adapter.")

    # Fetch data
    symbols = defn.tickers()
    all_symbols = symbols + ([defn.universe.benchmark_symbol] if defn.universe.benchmark_symbol not in symbols else [])
    bars_by_symbol = await fetch_bars_multi(all_symbols, defn.data.start_date, defn.data.end_date)

    missing = [s for s in symbols if not bars_by_symbol.get(s)]
    if missing:
        raise HTTPException(422, f"Could not fetch data for: {missing}")

    # Persist DataSnapshot
    strategy_bars = {s: bars_by_symbol[s] for s in symbols}
    manifest = build_snapshot_manifest(bars_by_symbol, all_symbols, defn.data.start_date, defn.data.end_date, "fmp_yahoo")
    snap_hash = content_hash(bars_by_symbol)
    total_rows = sum(len(b) for b in bars_by_symbol.values())

    snapshot_id = _new_id()
    snapshot = DataSnapshot(
        id=snapshot_id,
        symbols_json=json.dumps(all_symbols),
        start_date=defn.data.start_date,
        end_date=defn.data.end_date,
        source="fmp_yahoo",
        row_count=total_rows,
        manifest_json=json.dumps(manifest),
        content_hash=snap_hash,
        created_at=_now(),
    )
    db.add(snapshot)
    await db.flush()

    # Run validation in thread (CPU-bound)
    benchmark_bars = bars_by_symbol.get(defn.universe.benchmark_symbol, [])
    is_portfolio = len(symbols) > 1

    if is_portfolio:
        val_input = strategy_bars
    else:
        val_input = strategy_bars.get(symbols[0], [])

    val_result = await asyncio.to_thread(
        run_rolling_folds,
        val_input,
        plan,
        10000.0,   # standardized capital for validation
        req.n_folds,
        req.holdout_pct,
        req.bootstrap_sims,
    )

    # Persist ValidationReport
    report_id = _new_id()
    report = ValidationReport(
        id=report_id,
        strategy_version_id=version_id,
        data_snapshot_id=snapshot_id,
        fold_results_json=json.dumps([f.model_dump() for f in val_result.folds]),
        holdout_json=json.dumps(val_result.holdout),
        bootstrap_json=json.dumps(val_result.bootstrap),
        regime_json=json.dumps(val_result.regime_breakdown),
        summary_json=json.dumps(val_result.summary),
        gate_results_json=json.dumps({"warnings": val_result.warnings}),
        status="complete",
        created_at=_now(),
    )
    db.add(report)
    await db.commit()

    return {
        "validation_report_id": report_id,
        "data_snapshot_id": snapshot_id,
        "summary": val_result.summary,
        "folds": [f.model_dump() for f in val_result.folds],
        "holdout": val_result.holdout,
        "bootstrap": val_result.bootstrap,
        "regime_breakdown": val_result.regime_breakdown,
        "warnings": val_result.warnings,
    }


@router.post("/{strategy_id}/versions/{version_id}/backtest")
async def run_backtest(
    strategy_id: str,
    version_id: str,
    req: BacktestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Run a backtest against a validated strategy version.
    Persists DataSnapshot + SimulationRun linked to the strategy version.
    """
    version = await db.get(StrategyVersion, version_id)
    if not version or version.strategy_id != strategy_id:
        raise HTTPException(404, "Version not found")

    defn = _load_definition(version)
    plan = compile_strategy(defn)
    if not plan.is_runnable:
        raise HTTPException(422, {
            "message": "Version has blocking errors and cannot be run.",
            "findings": plan.findings,
        })

    cap = get_capability()
    if defn.data.price_basis == "total_return" and not cap.total_return_verified:
        raise HTTPException(422, "total_return is not supported by the current data adapter.")

    symbols = defn.tickers()
    all_symbols = list(set(symbols + [req.benchmark_symbol]))
    bars_by_symbol = await fetch_bars_multi(all_symbols, defn.data.start_date, defn.data.end_date)

    missing = [s for s in symbols if not bars_by_symbol.get(s)]
    if missing:
        raise HTTPException(422, f"No data for symbols: {missing}")

    # Persist DataSnapshot
    manifest = build_snapshot_manifest(bars_by_symbol, all_symbols, defn.data.start_date, defn.data.end_date, "fmp_yahoo")
    snap_hash = content_hash(bars_by_symbol)
    total_rows = sum(len(b) for b in bars_by_symbol.values())

    snapshot_id = _new_id()
    snapshot = DataSnapshot(
        id=snapshot_id,
        symbols_json=json.dumps(all_symbols),
        start_date=defn.data.start_date,
        end_date=defn.data.end_date,
        source="fmp_yahoo",
        row_count=total_rows,
        manifest_json=json.dumps(manifest),
        content_hash=snap_hash,
        created_at=_now(),
    )
    db.add(snapshot)
    await db.flush()

    benchmark_bars = bars_by_symbol.get(req.benchmark_symbol, [])
    is_portfolio = len(symbols) > 1

    if is_portfolio:
        engine_input = {s: bars_by_symbol[s] for s in symbols}
        result = await asyncio.to_thread(
            run_portfolio, engine_input, plan, req.initial_capital, benchmark_bars
        )
    else:
        result = await asyncio.to_thread(
            run_single, bars_by_symbol[symbols[0]], plan, req.initial_capital, benchmark_bars
        )

    # Run block bootstrap MC if requested
    mc_result = None
    if req.run_monte_carlo and result.get("daily_returns"):
        from backend.services.strategy.validation_protocol import _block_bootstrap_mc
        mc_result = await asyncio.to_thread(
            _block_bootstrap_mc,
            result["daily_returns"],
            req.initial_capital,
            req.monte_carlo_sims,
        )

    # Persist SimulationRun
    run_id = _new_id()
    summary = result.get("summary", {})
    full_payload = {
        **result,
        "monte_carlo": mc_result,
        "data_snapshot_id": snapshot_id,
        "strategy_version_id": version_id,
    }
    # Remove large daily_returns from summary (keep in result_json)
    sim_run = SimulationRun(
        id=run_id,
        created_at=_now(),
        mode="portfolio" if is_portfolio else "single",
        strategy_description=version.source_prompt,
        symbol=symbols[0] if not is_portfolio else None,
        holdings_json=json.dumps([{"ticker": s} for s in symbols]) if is_portfolio else None,
        parsed_strategy_json=version.definition_json,
        start_date=defn.data.start_date,
        end_date=defn.data.end_date,
        initial_capital=req.initial_capital,
        benchmark_symbol=req.benchmark_symbol,
        commission_bps=defn.costs.commission_bps,
        slippage_bps=defn.costs.base_slippage_bps,
        request_json=json.dumps({
            "strategy_version_id": version_id,
            "initial_capital": req.initial_capital,
            "benchmark_symbol": req.benchmark_symbol,
        }),
        summary_json=json.dumps(summary),
        result_json=json.dumps(full_payload, default=str),
        strategy_version_id=version_id,
        data_snapshot_id=snapshot_id,
    )
    db.add(sim_run)
    await db.commit()

    return {
        "simulation_run_id": run_id,
        "data_snapshot_id": snapshot_id,
        "strategy_version_id": version_id,
        "summary": summary,
        "equity_curve": result.get("equity_curve", []),
        "trades": result.get("trades", [])[:100],  # cap for response size
        "trade_count": len(result.get("trades", [])),
        "monte_carlo": mc_result,
        "per_ticker": result.get("per_ticker"),
        "findings": plan.findings,
    }
