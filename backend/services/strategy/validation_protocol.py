"""
Validation protocol — rolling chronological folds, final holdout, block-bootstrap MC.

Replaces the old single 70/30 split and i.i.d. bootstrap.
No I/O, no LLM.
"""
from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from backend.services.strategy.schema import CompiledPlan
    from backend.services.strategy.data_adapter import BarRecord


class FoldResult(BaseModel):
    fold_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_metrics: dict
    test_metrics: dict
    overfit_flag: bool   # heuristic: train_sharpe > 0.5 and test_sharpe < 0


class ValidationResult(BaseModel):
    folds: list[FoldResult]
    holdout: dict
    bootstrap: dict
    regime_breakdown: dict
    summary: dict
    warnings: list[str]


# ── Regime labelling ──────────────────────────────────────────────────────────

def _sma(values: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(values)
    for i in range(lookback - 1, len(values)):
        result[i] = sum(values[i - lookback + 1: i + 1]) / lookback
    return result


def label_regimes(bars: "list[BarRecord]", sma_lookback: int = 200) -> list[str]:
    """
    Assign 'bull'/'bear'/'sideways' per bar using 200-day SMA.
    Uses only past data — no lookahead.
    """
    closes = [b["close"] for b in bars]
    sma200 = _sma(closes, sma_lookback)
    labels: list[str] = []
    for i, sma in enumerate(sma200):
        if sma is None:
            labels.append("sideways")
        else:
            ratio = closes[i] / sma
            if ratio > 1.10:
                labels.append("bull")
            elif ratio < 0.90:
                labels.append("bear")
            else:
                labels.append("sideways")
    return labels


# ── Rolling folds ─────────────────────────────────────────────────────────────

def run_rolling_folds(
    bars: "list[BarRecord] | dict[str, list[BarRecord]]",
    plan: "CompiledPlan",
    initial_capital: float,
    n_folds: int = 5,
    holdout_pct: float = 0.20,
    bootstrap_sims: int = 300,
    seed: int = 42,
) -> ValidationResult:
    """
    Validation protocol:
    1. Reserve final holdout_pct of bars as untouched holdout.
    2. Split remaining into n_folds rolling chronological folds.
    3. Block-bootstrap MC on non-holdout returns.
    """
    from backend.services.strategy.engine import run_single, run_portfolio
    from backend.services.strategy.metrics import compute_all, sharpe as calc_sharpe

    warnings: list[str] = []

    # Normalize to a single bar list for date-indexing (use first symbol for portfolio)
    if isinstance(bars, dict):
        # Use the benchmark or first symbol's bar dates as the master timeline
        first_sym = next(iter(bars))
        master_bars = bars[first_sym]
        is_portfolio = True
    else:
        master_bars = bars
        is_portfolio = False

    n = len(master_bars)
    if n < 60:
        warnings.append("Too few bars for rolling validation (need >= 60).")
        return ValidationResult(
            folds=[],
            holdout={},
            bootstrap={},
            regime_breakdown={},
            summary={},
            warnings=warnings,
        )

    # ── Holdout split ─────────────────────────────────────────────────────────
    holdout_start_idx = max(int(n * (1 - holdout_pct)), 10)
    non_holdout_bars = master_bars[:holdout_start_idx]
    holdout_master = master_bars[holdout_start_idx:]

    warmup = plan.warmup_bars + plan.definition.execution.order_delay_bars

    # ── Rolling folds on non-holdout ─────────────────────────────────────────
    nh = len(non_holdout_bars)
    folds: list[FoldResult] = []

    if n_folds < 1:
        n_folds = 1
    step = max((nh - warmup) // (n_folds + 1), 10)
    train_bars_target = min(step * 3, nh - step)

    actual_folds = min(n_folds, (nh - warmup) // max(step, 1))
    if actual_folds < 1:
        warnings.append("Insufficient data for rolling folds — using single fold.")
        actual_folds = 1

    for fold_i in range(actual_folds):
        test_start_idx = warmup + (fold_i + 1) * step
        test_end_idx = min(test_start_idx + step, nh)
        train_end_idx = test_start_idx
        train_start_idx = max(0, train_end_idx - train_bars_target)

        if test_start_idx >= nh:
            break

        train_slice = _slice_bars(bars, train_start_idx, train_end_idx, is_portfolio, first_sym if is_portfolio else None)
        test_slice = _slice_bars(bars, test_start_idx, test_end_idx, is_portfolio, first_sym if is_portfolio else None)

        if is_portfolio:
            train_res = run_portfolio(train_slice, plan, initial_capital)
            test_res = run_portfolio(test_slice, plan, initial_capital)
        else:
            train_res = run_single(train_slice, plan, initial_capital)
            test_res = run_single(test_slice, plan, initial_capital)

        train_sharpe = train_res["summary"].get("sharpe", 0)
        test_sharpe = test_res["summary"].get("sharpe", 0)

        folds.append(FoldResult(
            fold_index=fold_i,
            train_start=non_holdout_bars[train_start_idx]["date"],
            train_end=non_holdout_bars[min(train_end_idx - 1, nh - 1)]["date"],
            test_start=non_holdout_bars[test_start_idx]["date"],
            test_end=non_holdout_bars[min(test_end_idx - 1, nh - 1)]["date"],
            train_metrics=train_res["summary"],
            test_metrics=test_res["summary"],
            overfit_flag=(train_sharpe > 0.5 and test_sharpe < 0),
        ))

    # ── Holdout run ───────────────────────────────────────────────────────────
    holdout_slice = _slice_bars(
        bars, holdout_start_idx, n, is_portfolio,
        first_sym if is_portfolio else None,
    )
    if is_portfolio and isinstance(holdout_slice, dict) and holdout_slice:
        holdout_res = run_portfolio(holdout_slice, plan, initial_capital)
    elif not is_portfolio and isinstance(holdout_slice, list) and holdout_slice:
        holdout_res = run_single(holdout_slice, plan, initial_capital)
    else:
        holdout_res = {"summary": {}, "daily_returns": [], "equity_curve": []}
        warnings.append("Could not run holdout — insufficient bars.")

    # ── Block-bootstrap MC on non-holdout returns ─────────────────────────────
    # Get returns from a full non-holdout run
    if is_portfolio:
        full_nonholdout_slice = _slice_bars(bars, 0, holdout_start_idx, True, first_sym)
        full_res = run_portfolio(full_nonholdout_slice, plan, initial_capital)
    else:
        full_nonholdout_slice = _slice_bars(bars, 0, holdout_start_idx, False, None)
        full_res = run_single(full_nonholdout_slice, plan, initial_capital)

    non_holdout_returns = full_res.get("daily_returns", [])
    bootstrap = _block_bootstrap_mc(
        non_holdout_returns,
        initial_capital,
        n_sims=bootstrap_sims,
        block_size=21,
        seed=seed,
    )
    if "error" in bootstrap:
        warnings.append(bootstrap["error"])

    # ── Regime breakdown on holdout ───────────────────────────────────────────
    regime_labels = label_regimes(master_bars)
    holdout_labels = regime_labels[holdout_start_idx:]
    holdout_returns = holdout_res.get("daily_returns", [])
    regime_breakdown = _regime_metrics(holdout_returns, holdout_labels)

    # ── Summary ───────────────────────────────────────────────────────────────
    oos_sharpes = [f.test_metrics.get("sharpe", 0) for f in folds]
    mean_oos_sharpe = sum(oos_sharpes) / len(oos_sharpes) if oos_sharpes else 0
    train_sharpes = [f.train_metrics.get("sharpe", 0) for f in folds]
    mean_train_sharpe = sum(train_sharpes) / len(train_sharpes) if train_sharpes else 0
    degradation = (
        (mean_train_sharpe - mean_oos_sharpe) / abs(mean_train_sharpe)
        if mean_train_sharpe != 0 else 0
    )

    summary = {
        "n_folds": len(folds),
        "holdout_pct": holdout_pct,
        "holdout_bars": len(holdout_master),
        "mean_oos_sharpe": mean_oos_sharpe,
        "mean_train_sharpe": mean_train_sharpe,
        "sharpe_degradation_pct": degradation * 100,
        "n_overfit_flags": sum(1 for f in folds if f.overfit_flag),
        "bootstrap_sims": bootstrap_sims,
        "holdout_metrics": holdout_res.get("summary", {}),
    }

    return ValidationResult(
        folds=folds,
        holdout=holdout_res.get("summary", {}),
        bootstrap=bootstrap,
        regime_breakdown=regime_breakdown,
        summary=summary,
        warnings=warnings,
    )


def _slice_bars(bars, start: int, end: int, is_portfolio: bool, first_sym: Optional[str]):
    if is_portfolio:
        return {sym: b[start:end] for sym, b in bars.items()}
    return bars[start:end]


def _block_bootstrap_mc(
    daily_returns: list[float],
    initial_capital: float,
    n_sims: int = 300,
    block_size: int = 21,
    seed: int = 42,
) -> dict:
    """
    Block bootstrap preserving local autocorrelation.
    Returns percentile fan (p5/p25/p50/p75/p95) and terminal distribution stats.
    """
    rng = random.Random(seed)

    n = len(daily_returns)
    if n < block_size * 3:
        return {
            "error": f"Too few return observations ({n}) for block bootstrap (need >= {block_size * 3}).",
            "paths": [],
            "percentiles": {},
        }

    n_blocks_per_path = math.ceil(n / block_size)
    blocks = [daily_returns[i: i + block_size] for i in range(0, n - block_size + 1)]

    paths: list[list[float]] = []
    for _ in range(n_sims):
        sampled: list[float] = []
        for _ in range(n_blocks_per_path):
            block = rng.choice(blocks)
            sampled.extend(block)
        sampled = sampled[:n]
        equity = initial_capital
        path: list[float] = [equity]
        for r in sampled:
            equity *= (1 + r)
            path.append(round(equity, 2))
        paths.append(path)

    path_len = len(paths[0]) if paths else 0
    pct_keys = [5, 25, 50, 75, 95]
    percentiles: dict[str, list[float]] = {str(p): [] for p in pct_keys}

    for t in range(path_len):
        values_at_t = sorted(p[t] for p in paths)
        for pct in pct_keys:
            idx = int(pct / 100 * len(values_at_t))
            idx = min(idx, len(values_at_t) - 1)
            percentiles[str(pct)].append(values_at_t[idx])

    terminals = [p[-1] for p in paths]
    return {
        "n_sims": n_sims,
        "block_size": block_size,
        "seed": seed,
        "n_bars": n,
        "percentiles": percentiles,
        "terminal_p5": sorted(terminals)[int(0.05 * len(terminals))],
        "terminal_p50": sorted(terminals)[int(0.50 * len(terminals))],
        "terminal_p95": sorted(terminals)[int(0.95 * len(terminals))],
    }


def _regime_metrics(returns: list[float], labels: list[str]) -> dict:
    """Break down mean return and vol by regime label."""
    regime_data: dict[str, list[float]] = {"bull": [], "bear": [], "sideways": []}
    for r, lbl in zip(returns, labels):
        if lbl in regime_data:
            regime_data[lbl].append(r)

    result: dict = {}
    for regime, rets in regime_data.items():
        n = len(rets)
        if n == 0:
            result[regime] = {"n_bars": 0, "mean_daily_return_pct": 0, "volatility_ann_pct": 0}
            continue
        mean_r = sum(rets) / n * 100
        if n > 1:
            mean_val = sum(rets) / n
            var = sum((r - mean_val) ** 2 for r in rets) / (n - 1)
            vol = math.sqrt(var) * math.sqrt(252) * 100
        else:
            vol = 0
        result[regime] = {
            "n_bars": n,
            "mean_daily_return_pct": round(mean_r, 4),
            "volatility_ann_pct": round(vol, 2),
        }
    return result
