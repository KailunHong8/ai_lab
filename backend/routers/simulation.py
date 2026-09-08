"""
Strategy simulation with institutional-grade analytics.

LLM parsing: Bedrock or Ollama (provider toggle).
Backtesting: pure-Python rule replay (vectorbt optional, loaded lazily).
Analytics:
  - Sharpe, Sortino, Calmar ratios
  - Max drawdown, average drawdown, recovery time
  - Beta / Alpha vs benchmark (SPY)
  - Factor exposure proxy (momentum, value flag)
  - Monte Carlo simulation (return distribution, percentile fan)
  - Walk-forward validation (in-sample / out-of-sample split)
  - Stress test overlays (2008 GFC, 2020 COVID, 2022 rate shock)
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
from typing import Optional

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.services import fmp as fmp_service

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

PARSE_SYSTEM = (
    "You are a quantitative strategy parser. "
    "Given a natural-language description of a trading strategy, extract the following JSON fields:\n"
    "  - buy_condition: string description of when to buy\n"
    "  - sell_condition: string description of when to sell\n"
    "  - buy_pct_drop: float | null — % drop from previous close that triggers a buy (positive)\n"
    "  - sell_pct_gain: float | null — % gain from buy price that triggers a sell\n"
    "  - stop_loss_pct: float | null — % loss from buy price for stop-loss\n"
    "  - hold_days: int | null — max holding period in trading days\n"
    "Return ONLY a JSON object with these fields."
)

PARSE_DUAL_SYSTEM = (
    "You are a quantitative strategy parser. "
    "Given a natural-language or tabular description of a trading strategy, extract:\n\n"
    "1. holdings: array of portfolio positions from any allocation table. Each entry:\n"
    "   - ticker: string (uppercase, e.g. AAPL, BRK.B)\n"
    "   - allocation_pct: float (percentage, e.g. 14.0 for 14%)\n"
    "   - sector: string | null\n"
    "   - tier: string | null\n"
    "   - rationale: string | null\n"
    "   Return [] if no allocation table is present.\n\n"
    "2. trading_rules: object with:\n"
    "   - buy_condition: string | null\n"
    "   - sell_condition: string | null\n"
    "   - buy_pct_drop: float | null — % drop from previous close that triggers a buy (positive)\n"
    "   - sell_pct_gain: float | null — % gain from buy price that triggers a sell\n"
    "   - stop_loss_pct: float | null — % loss from buy price for stop-loss\n"
    "   - hold_days: int | null — max holding period in trading days\n"
    "   Return all null if no explicit trading rules are present.\n\n"
    'Return ONLY valid JSON: {"holdings": [...], "trading_rules": {...}}'
)

# Default rules for allocation-only strategies: buy on first available day, hold until end
DEFAULT_ALLOCATION_RUN_RULES: dict = {
    "buy_condition": "Buy and hold from start date",
    "sell_condition": None,
    "buy_pct_drop": 0.0,
    "sell_pct_gain": None,
    "stop_loss_pct": None,
    "hold_days": None,
}

# Historical date ranges for stress-test overlays
STRESS_PERIODS = {
    "2008_gfc":       ("2008-01-01", "2009-06-30", "2008 GFC"),
    "2020_covid":     ("2020-02-01", "2020-12-31", "2020 COVID"),
    "2022_rate_shock":("2022-01-01", "2022-12-31", "2022 Rate Shock"),
}


# ── LLM parsing (provider-agnostic) ──────────────────────────────────────────

async def _parse_strategy_dual(description: str, provider: str, model: Optional[str]) -> dict:
    """Parse strategy into holdings + trading_rules. Returns raw LLM dict."""
    raw = await _llm_extract(description, PARSE_DUAL_SYSTEM, provider, model)
    holdings_raw = raw.get("holdings") or []
    trading_rules_raw = raw.get("trading_rules") or {}

    # Normalize holdings
    parse_warnings: list[str] = []
    holdings: list[dict] = []
    seen_tickers: dict[str, int] = {}

    for i, h in enumerate(holdings_raw):
        ticker = str(h.get("ticker", "")).upper().strip()
        alloc = h.get("allocation_pct")

        if not ticker:
            parse_warnings.append(f"Row {i + 1} missing ticker; skipped")
            continue
        try:
            alloc = float(alloc)
        except (TypeError, ValueError):
            parse_warnings.append(f"Row {i + 1} ({ticker}) has invalid allocation; skipped")
            continue
        if alloc <= 0:
            parse_warnings.append(f"Row {i + 1} ({ticker}) has non-positive allocation; skipped")
            continue

        if h.get("tier") is None:
            parse_warnings.append(f"Row {i + 1} ({ticker}) missing tier; defaulted to 'Unknown'")

        if ticker in seen_tickers:
            orig_idx = seen_tickers[ticker]
            holdings[orig_idx]["allocation_pct"] += alloc
            parse_warnings.append(f"Duplicate ticker {ticker}; allocations merged")
        else:
            seen_tickers[ticker] = len(holdings)
            holdings.append({
                "ticker": ticker,
                "allocation_pct": alloc,
                "sector": h.get("sector"),
                "tier": h.get("tier") or "Unknown",
                "rationale": h.get("rationale"),
            })

    # Normalize allocation total to 100 if needed
    total = sum(h["allocation_pct"] for h in holdings)
    if holdings and abs(total - 100.0) > 0.1:
        factor = 100.0 / total
        for h in holdings:
            h["allocation_pct"] = round(h["allocation_pct"] * factor, 4)
        parse_warnings.append(f"Total allocation was {round(total, 2)}%; normalised to 100%")

    # Determine strategy_mode
    has_holdings = bool(holdings)
    rules = trading_rules_raw or {}
    has_rules = any(
        rules.get(k) is not None
        for k in ("buy_pct_drop", "sell_pct_gain", "stop_loss_pct", "hold_days")
    )

    if has_holdings and has_rules:
        strategy_mode = "allocation_and_rules"
    elif has_holdings:
        strategy_mode = "allocation_only"
    else:
        strategy_mode = "rules_only"

    return {
        "holdings": holdings,
        "trading_rules": rules,
        "parse_warnings": parse_warnings,
        "strategy_mode": strategy_mode,
    }


async def _llm_extract(description: str, system_prompt: str, provider: str, model: Optional[str]) -> dict:
    """Low-level LLM call returning a parsed dict."""
    if provider in ("ollama", "ollama-cloud"):
        from backend.services import ollama_client
        if provider == "ollama-cloud":
            _api_key = os.getenv("OLLAMA_API_KEY", "")
            if not _api_key:
                raise ValueError("OLLAMA_API_KEY not set")
            _model = model or ollama_client.OLLAMA_CLOUD_DEFAULT_MODEL
            result = await ollama_client.extract_json(
                description, system_prompt, model=_model,
                host=ollama_client.OLLAMA_CLOUD_HOST, api_key=_api_key,
            )
        else:
            _model = model or ollama_client.OLLAMA_DEFAULT_MODEL
            result = await ollama_client.extract_json(description, system_prompt, model=_model)
        if result and result != {"theses": [], "relationships": []}:
            return result
        raise ValueError("Ollama returned no parseable JSON")
    else:
        import boto3
        region = os.getenv("BEDROCK_REGION", "eu-west-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
        client = boto3.client("bedrock-runtime", region_name=region)
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system_prompt}],
            messages=[{"role": "user", "content": [{"text": description}]}],
        )
        text = resp["output"]["message"]["content"][0]["text"]
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end])


async def _parse_strategy(description: str, provider: str, model: Optional[str]) -> dict:
    return await _llm_extract(description, PARSE_SYSTEM, provider, model)


# ── Transaction cost model ─────────────────────────────────────────────────────
# Fixed-bps slippage applied as a price haircut on BOTH legs, plus a bps commission
# charged on each fill's notional. This is the standard daily-bar, fill-at-close
# approach (Zipline / Backtrader / vectorbt). We deliberately avoid square-root
# market-impact / Almgren-Chriss models: those are intraday execution-scheduling
# models and are unidentifiable at daily-close granularity.
#
# Defaults are sensible for US large-caps. Raise slippage for smaller / illiquid
# names (≈10 bps mid-cap, 20–50 bps small-cap).
DEFAULT_COMMISSION_BPS = 2.0   # institutional all-in; set 0.0 for commission-free retail
DEFAULT_SLIPPAGE_BPS   = 5.0   # US large-cap one-way; raise for smaller names


# ── Core backtest engine ──────────────────────────────────────────────────────

def _run_backtest(
    candles: list[dict],
    rules: dict,
    initial_capital: float,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> dict:
    """
    Rule-based replay. Returns equity curve, trades, and raw return series.
    candles sorted oldest-first: [{"date", "open", "high", "low", "close"}, ...]

    Transaction costs: slippage moves the fill price against us on each leg
    (buy higher, sell lower); commission is a bps charge on notional, subtracted
    from cash on every fill. Positions are marked-to-market at the raw close —
    costs are realised only at trade time.
    """
    cash = initial_capital
    shares = 0.0
    buy_price = 0.0
    buy_day = 0
    trades: list[dict] = []
    equity_curve: list[dict] = []
    daily_returns: list[float] = []

    buy_pct_drop  = rules.get("buy_pct_drop")
    sell_pct_gain = rules.get("sell_pct_gain")
    stop_loss_pct = rules.get("stop_loss_pct")
    hold_days     = rules.get("hold_days")

    slip = slippage_bps / 10000.0
    comm = commission_bps / 10000.0

    total_costs = 0.0
    prev_portfolio = initial_capital

    for i, candle in enumerate(candles):
        close      = float(candle["close"])
        prev_close = float(candles[i - 1]["close"]) if i > 0 else close

        if shares == 0 and buy_pct_drop is not None:
            drop = (prev_close - close) / prev_close * 100
            if drop >= buy_pct_drop and cash > 0:
                fill_price = close * (1 + slip)            # pay more on entry
                # Reserve for commission so cash never goes negative
                shares     = cash / (fill_price * (1 + comm))
                gross      = shares * fill_price
                commission = gross * comm
                cash       = cash - gross - commission
                buy_price  = fill_price
                buy_day    = i
                total_costs += commission + shares * (fill_price - close)
                trades.append({"date": candle["date"], "action": "BUY", "price": round(fill_price, 4)})

        elif shares > 0:
            gain = (close - buy_price) / buy_price * 100
            loss = (buy_price - close) / buy_price * 100
            days_held = i - buy_day
            should_sell = (
                (sell_pct_gain is not None and gain >= sell_pct_gain)
                or (stop_loss_pct is not None and loss >= stop_loss_pct)
                or (hold_days is not None and days_held >= hold_days)
            )
            if should_sell:
                fill_price = close * (1 - slip)            # receive less on exit
                gross      = shares * fill_price
                commission = gross * comm
                cash       = cash + gross - commission
                total_costs += commission + shares * (close - fill_price)
                shares     = 0.0
                trades.append({"date": candle["date"], "action": "SELL", "price": round(fill_price, 4)})

        portfolio_value = cash + shares * close
        equity_curve.append({"date": candle["date"], "value": round(portfolio_value, 2)})

        ret = (portfolio_value - prev_portfolio) / prev_portfolio if prev_portfolio else 0.0
        daily_returns.append(ret)
        prev_portfolio = portfolio_value

    if shares > 0 and candles:
        close      = float(candles[-1]["close"])
        fill_price = close * (1 - slip)
        gross      = shares * fill_price
        commission = gross * comm
        cash       = cash + gross - commission
        total_costs += commission + shares * (close - fill_price)
        shares = 0.0

    return {
        "equity_curve": equity_curve,
        "trades": trades,
        "daily_returns": daily_returns,
        "final_value": cash,
        "total_costs": round(total_costs, 2),
    }


# ── Institutional risk / performance metrics ──────────────────────────────────

TRADING_DAYS = 252
RISK_FREE_DAILY = 0.05 / TRADING_DAYS  # 5% annual risk-free rate


def _metrics(
    daily_returns: list[float],
    initial_capital: float,
    final_value: float,
    equity_curve: list[dict],
    benchmark_returns: list[float] | None = None,
) -> dict:
    n = len(daily_returns)
    if n == 0:
        return {}

    rets = daily_returns
    excess = [r - RISK_FREE_DAILY for r in rets]

    # ── Sharpe ────
    mean_excess = sum(excess) / n
    std_all = math.sqrt(sum((r - mean_excess) ** 2 for r in excess) / max(n - 1, 1))
    sharpe = (mean_excess / std_all * math.sqrt(TRADING_DAYS)) if std_all else 0.0

    # ── Sortino (downside deviation) ────
    downside = [r for r in excess if r < 0]
    if downside:
        dd_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
        sortino = (mean_excess / dd_std * math.sqrt(TRADING_DAYS)) if dd_std else 0.0
    else:
        sortino = float("inf")

    # ── Max drawdown & Calmar ────
    peak = initial_capital
    max_dd_pct = 0.0
    drawdown_series: list[float] = []
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak else 0.0
        drawdown_series.append(dd)
        if dd > max_dd_pct:
            max_dd_pct = dd

    years = n / TRADING_DAYS
    annual_return_pct = ((final_value / initial_capital) ** (1 / max(years, 0.01)) - 1) * 100
    calmar = annual_return_pct / max_dd_pct if max_dd_pct else float("inf")

    avg_dd = sum(drawdown_series) / len(drawdown_series) if drawdown_series else 0.0

    # ── Beta / Alpha ────
    beta, alpha_ann = None, None
    if benchmark_returns and len(benchmark_returns) == n:
        bm_mean = sum(benchmark_returns) / n
        cov_num  = sum((rets[i] - (sum(rets)/n)) * (benchmark_returns[i] - bm_mean) for i in range(n))
        bm_var   = sum((b - bm_mean) ** 2 for b in benchmark_returns)
        beta     = (cov_num / bm_var) if bm_var else 0.0
        port_ann = ((1 + sum(rets) / n) ** TRADING_DAYS - 1)
        bm_ann   = ((1 + bm_mean) ** TRADING_DAYS - 1)
        alpha_ann = port_ann - (0.05 + beta * (bm_ann - 0.05))

    # ── Momentum factor proxy ────
    momentum_flag = None
    if n >= 60:
        recent_60 = sum(rets[-60:])
        momentum_flag = "positive" if recent_60 > 0 else "negative"

    pnl     = final_value - initial_capital
    pnl_pct = pnl / initial_capital * 100

    num_sell = sum(1 for t in [] if t)  # placeholder — computed in caller
    return {
        "pnl":              round(pnl, 2),
        "pnl_pct":          round(pnl_pct, 2),
        "annual_return_pct": round(annual_return_pct, 2),
        "sharpe":           round(sharpe, 3),
        "sortino":          round(min(sortino, 99.0), 3),
        "calmar":           round(min(calmar, 99.0), 3),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "avg_drawdown_pct": round(avg_dd, 2),
        "beta":             round(beta, 3) if beta is not None else None,
        "alpha_ann_pct":    round(alpha_ann * 100, 2) if alpha_ann is not None else None,
        "momentum_flag":    momentum_flag,
    }


def _trade_stats(trades: list[dict]) -> dict:
    buys  = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]
    pairs = list(zip(buys, sells))
    wins  = sum(1 for b, s in pairs if s["price"] > b["price"])
    return {
        "num_trades": len(sells),
        "win_rate":   round(wins / len(pairs), 4) if pairs else 0.0,
    }


# ── Monte Carlo simulation ────────────────────────────────────────────────────

def _monte_carlo(
    daily_returns: list[float],
    initial_capital: float,
    n_simulations: int = 500,
    horizon_days: Optional[int] = None,
) -> dict:
    """
    Bootstrap Monte Carlo: resample daily returns with replacement.
    Returns percentile fan (p5, p25, p50, p75, p95) over the horizon.
    """
    if not daily_returns:
        return {}

    n = horizon_days or len(daily_returns)
    n_sims = min(n_simulations, 1000)

    # Sample all paths at once using pure Python (no numpy required)
    all_finals: list[float] = []
    # Build percentile fan: store [p5, p25, p50, p75, p95] per day
    # To keep memory reasonable, record at every 5th day for long horizons
    step = max(1, n // 100)
    checkpoint_days = list(range(step, n + 1, step))
    if n not in checkpoint_days:
        checkpoint_days.append(n)

    # We run n_sims paths; store only checkpoints
    fan_accum: dict[int, list[float]] = {d: [] for d in checkpoint_days}

    for _ in range(n_sims):
        val = initial_capital
        day_idx = 0
        cp_set = set(checkpoint_days)
        for day in range(1, n + 1):
            r = random.choice(daily_returns)
            val *= (1 + r)
            if day in cp_set:
                fan_accum[day].append(round(val, 2))
        all_finals.append(val)

    all_finals.sort()
    total = len(all_finals)

    def _pct(lst: list[float], p: float) -> float:
        idx = int(p / 100 * (len(lst) - 1))
        return round(lst[idx], 2)

    # Build fan curve
    fan: list[dict] = []
    for day in checkpoint_days:
        vals = sorted(fan_accum[day])
        fan.append({
            "day":  day,
            "p5":   _pct(vals, 5),
            "p25":  _pct(vals, 25),
            "p50":  _pct(vals, 50),
            "p75":  _pct(vals, 75),
            "p95":  _pct(vals, 95),
        })

    return {
        "n_simulations":   n_sims,
        "horizon_days":    n,
        "p5_final":        _pct(all_finals, 5),
        "p25_final":       _pct(all_finals, 25),
        "p50_final":       _pct(all_finals, 50),
        "p75_final":       _pct(all_finals, 75),
        "p95_final":       _pct(all_finals, 95),
        "prob_profit_pct": round(sum(1 for v in all_finals if v > initial_capital) / total * 100, 1),
        "fan_curve":       fan,
    }


# ── Walk-forward validation ───────────────────────────────────────────────────

def _walk_forward(
    candles: list[dict],
    rules: dict,
    initial_capital: float,
    in_sample_pct: float = 0.7,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> dict:
    """
    Split candles into in-sample (IS) and out-of-sample (OOS) windows.
    Run backtest on each. Compare metrics to detect overfitting.
    """
    split = int(len(candles) * in_sample_pct)
    if split < 20 or (len(candles) - split) < 10:
        return {"error": "Not enough data for walk-forward split"}

    is_candles  = candles[:split]
    oos_candles = candles[split:]

    is_res  = _run_backtest(is_candles,  rules, initial_capital, commission_bps, slippage_bps)
    oos_res = _run_backtest(oos_candles, rules, initial_capital, commission_bps, slippage_bps)

    def _pnl_pct(res: dict) -> float:
        return round((res["final_value"] - initial_capital) / initial_capital * 100, 2)

    is_pnl  = _pnl_pct(is_res)
    oos_pnl = _pnl_pct(oos_res)
    overfit_flag = is_pnl > 5 and oos_pnl < 0  # classic overfit signal

    return {
        "in_sample_days":      len(is_candles),
        "out_of_sample_days":  len(oos_candles),
        "in_sample_pnl_pct":   is_pnl,
        "out_of_sample_pnl_pct": oos_pnl,
        "overfit_warning":     overfit_flag,
        "in_sample_equity":    is_res["equity_curve"],
        "out_of_sample_equity": oos_res["equity_curve"],
    }


def _portfolio_walk_forward(
    candles_per_ticker: list[list[dict]],
    tickers: list[str],
    weights: list[float],
    rules: dict,
    initial_capital: float,
    in_sample_pct: float = 0.7,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> dict:
    """
    Walk-forward on the full blended portfolio (not a single-ticker proxy).
    Each leg is split into IS/OOS at the same fraction, backtested with its
    weighted capital slice, then blended into one IS curve and one OOS curve.
    """
    # Require every leg to have enough data for a meaningful split
    min_len = min(len(c) for c in candles_per_ticker) if candles_per_ticker else 0
    split = int(min_len * in_sample_pct)
    if split < 20 or (min_len - split) < 10:
        return {"error": "Not enough data for walk-forward split"}

    is_legs:  list[dict] = []
    oos_legs: list[dict] = []
    for candles, weight in zip(candles_per_ticker, weights):
        leg_cap   = initial_capital * weight
        leg_split = int(len(candles) * in_sample_pct)
        is_legs.append(_run_backtest(candles[:leg_split], rules, leg_cap, commission_bps, slippage_bps))
        oos_legs.append(_run_backtest(candles[leg_split:], rules, leg_cap, commission_bps, slippage_bps))

    is_blended  = _align_portfolio(is_legs,  tickers, weights, initial_capital)
    oos_blended = _align_portfolio(oos_legs, tickers, weights, initial_capital)

    def _pnl_pct(blended: dict) -> float:
        return round((blended["final_value"] - initial_capital) / initial_capital * 100, 2)

    is_pnl  = _pnl_pct(is_blended)
    oos_pnl = _pnl_pct(oos_blended)
    overfit_flag = is_pnl > 5 and oos_pnl < 0

    return {
        "in_sample_days":      len(is_blended["equity_curve"]),
        "out_of_sample_days":  len(oos_blended["equity_curve"]),
        "in_sample_pnl_pct":   is_pnl,
        "out_of_sample_pnl_pct": oos_pnl,
        "overfit_warning":     overfit_flag,
        "in_sample_equity":    is_blended["equity_curve"],
        "out_of_sample_equity": oos_blended["equity_curve"],
    }


# ── Stress tests ──────────────────────────────────────────────────────────────

async def _stress_tests(
    symbol: str,
    rules: dict,
    initial_capital: float,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> list[dict]:
    """Run the strategy over known crash/stress periods."""
    results = []
    for key, (start, end, label) in STRESS_PERIODS.items():
        candles = await fmp_service.get_history(symbol, start, end)
        if len(candles) < 10:
            results.append({"period": label, "error": "insufficient data"})
            continue
        res = _run_backtest(candles, rules, initial_capital, commission_bps, slippage_bps)
        pnl_pct = (res["final_value"] - initial_capital) / initial_capital * 100
        ts = _trade_stats(res["trades"])
        results.append({
            "period":       label,
            "start":        start,
            "end":          end,
            "pnl_pct":      round(pnl_pct, 2),
            "num_trades":   ts["num_trades"],
            "equity_curve": res["equity_curve"],
        })
    return results


# ── Portfolio backtest helpers ────────────────────────────────────────────────

def _align_portfolio(
    leg_results: list[dict],
    tickers: list[str],
    weights: list[float],
    initial_capital: float,
) -> dict:
    """
    Merge per-leg equity curves into a single portfolio equity curve.
    Each leg already runs with its weight × initial_capital slice, so we
    simply sum the daily values across legs on dates common to all legs.
    Returns blended equity_curve, daily_returns, final_value, and per-ticker info.
    """
    # Build date → value maps per leg
    leg_maps: list[dict[str, float]] = [
        {pt["date"]: pt["value"] for pt in r["equity_curve"]}
        for r in leg_results
    ]

    # Intersect dates (all legs must have data on that date)
    all_date_sets = [set(m.keys()) for m in leg_maps]
    common_dates = sorted(set.intersection(*all_date_sets)) if all_date_sets else []

    equity_curve: list[dict] = []
    daily_returns: list[float] = []
    prev_value = initial_capital

    for date in common_dates:
        total = sum(m[date] for m in leg_maps)
        equity_curve.append({"date": date, "value": round(total, 2)})
        ret = (total - prev_value) / prev_value if prev_value else 0.0
        daily_returns.append(ret)
        prev_value = total

    final_value = equity_curve[-1]["value"] if equity_curve else initial_capital

    # Per-ticker contribution
    per_ticker = []
    for i, (ticker, weight, res) in enumerate(zip(tickers, weights, leg_results)):
        leg_cap = initial_capital * weight
        leg_final = res["final_value"]
        leg_pnl_pct = (leg_final - leg_cap) / leg_cap * 100 if leg_cap else 0.0
        ts = _trade_stats(res["trades"])
        per_ticker.append({
            "ticker": ticker,
            "weight_pct": round(weight * 100, 1),
            "allocated": round(leg_cap, 2),
            "final_value": round(leg_final, 2),
            "pnl_pct": round(leg_pnl_pct, 2),
            "num_trades": ts["num_trades"],
            "win_rate": ts["win_rate"],
        })

    return {
        "equity_curve": equity_curve,
        "daily_returns": daily_returns,
        "final_value": final_value,
        "per_ticker": per_ticker,
    }


async def _portfolio_stress_tests(
    tickers: list[str],
    weights: list[float],
    rules: dict,
    initial_capital: float,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
) -> list[dict]:
    results = []
    for key, (start, end, label) in STRESS_PERIODS.items():
        leg_results = []
        valid = True
        for ticker, weight in zip(tickers, weights):
            candles = await fmp_service.get_history(ticker, start, end)
            if len(candles) < 10:
                valid = False
                break
            leg_cap = initial_capital * weight
            leg_results.append(_run_backtest(candles, rules, leg_cap, commission_bps, slippage_bps))
        if not valid:
            results.append({"period": label, "error": "insufficient data for one or more tickers"})
            continue
        blended = _align_portfolio(leg_results, tickers, weights, initial_capital)
        pnl_pct = (blended["final_value"] - initial_capital) / initial_capital * 100
        results.append({
            "period": label,
            "start": start,
            "end": end,
            "pnl_pct": round(pnl_pct, 2),
            "equity_curve": blended["equity_curve"],
        })
    return results


# ── Request / response models ─────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    strategy_description: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000.0
    provider: str = "bedrock"          # "bedrock", "ollama", or "ollama-cloud"
    model: Optional[str] = None
    run_monte_carlo: bool = True
    monte_carlo_sims: int = 300
    run_walk_forward: bool = True
    run_stress_tests: bool = True
    benchmark_symbol: str = "SPY"
    commission_bps: float = DEFAULT_COMMISSION_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS


class PortfolioHolding(BaseModel):
    ticker: str
    weight: float   # 0.0–1.0; weights are normalised server-side if they don't sum to 1


class ParseStrategyRequest(BaseModel):
    strategy_description: str
    provider: str = "bedrock"
    model: Optional[str] = None


class PortfolioSimulationRequest(BaseModel):
    strategy_description: str
    holdings: Optional[list[PortfolioHolding]] = None  # optional when auto_parse_holdings=True
    start_date: str
    end_date: str
    initial_capital: float = 10000.0
    provider: str = "bedrock"
    model: Optional[str] = None
    run_monte_carlo: bool = True
    monte_carlo_sims: int = 300
    run_walk_forward: bool = True
    run_stress_tests: bool = True
    benchmark_symbol: str = "SPY"
    commission_bps: float = DEFAULT_COMMISSION_BPS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS
    auto_parse_holdings: bool = True
    auto_parse_rules: bool = True
    strict_parse: bool = False


# ── SimulationRun helpers ─────────────────────────────────────────────────────

async def _persist_run(
    db: AsyncSession,
    *,
    mode: str,
    req_dict: dict,
    payload: dict,
    symbol: str | None = None,
    holdings: list[dict] | None = None,
    parsed_strategy: dict | None = None,
) -> str:
    """Persist a SimulationRun and return its id. Failures are swallowed."""
    from backend.models import SimulationRun
    run_id = str(uuid.uuid4())
    summary_keys = {
        "pnl", "pnl_pct", "annual_return_pct", "sharpe", "sortino", "calmar",
        "max_drawdown_pct", "avg_drawdown_pct", "beta", "alpha_ann_pct",
        "num_trades", "win_rate", "total_costs", "commission_bps", "slippage_bps",
    }
    summary = {k: payload[k] for k in summary_keys if k in payload}
    try:
        run = SimulationRun(
            id=run_id,
            mode=mode,
            strategy_description=req_dict.get("strategy_description"),
            symbol=symbol,
            holdings_json=json.dumps(holdings) if holdings else None,
            parsed_strategy_json=json.dumps(parsed_strategy) if parsed_strategy else None,
            start_date=req_dict["start_date"],
            end_date=req_dict["end_date"],
            initial_capital=req_dict.get("initial_capital", 10000),
            benchmark_symbol=req_dict.get("benchmark_symbol", "SPY"),
            commission_bps=req_dict.get("commission_bps", 0),
            slippage_bps=req_dict.get("slippage_bps", 0),
            provider=req_dict.get("provider"),
            model=req_dict.get("model"),
            request_json=json.dumps(req_dict),
            summary_json=json.dumps(summary),
            result_json=json.dumps(payload),
        )
        db.add(run)
        await db.commit()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("SimulationRun persist failed: %s", exc)
    return run_id


# ── Parse-strategy endpoint ──────────────────────────────────────────────────

@router.post("/parse-strategy")
async def parse_strategy_endpoint(req: ParseStrategyRequest):
    """Parse strategy_description into holdings + trading rules for preview/debug."""
    try:
        parsed = await _parse_strategy_dual(req.strategy_description, req.provider, req.model)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse strategy: {exc}")
    return parsed


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/run")
async def run_simulation(req: SimulationRequest, db: AsyncSession = Depends(get_db)):
    # 1. Fetch primary candles
    candles = await fmp_service.get_history(req.symbol, req.start_date, req.end_date)
    if not candles:
        raise HTTPException(404, f"No historical data for {req.symbol} in {req.start_date}–{req.end_date}")

    # 2. Parse strategy rules
    try:
        rules = await _parse_strategy(req.strategy_description, req.provider, req.model)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse strategy: {exc}")

    # 3. Fetch benchmark in parallel with backtest
    async def _bm_returns() -> list[float]:
        bm = await fmp_service.get_history(req.benchmark_symbol, req.start_date, req.end_date)
        if len(bm) != len(candles):
            return []
        closes = [float(c["close"]) for c in bm]
        return [(closes[i] - closes[i - 1]) / closes[i - 1] if i > 0 else 0.0
                for i in range(len(closes))]

    bt_result, bm_rets = await asyncio.gather(
        asyncio.to_thread(_run_backtest, candles, rules, req.initial_capital,
                          req.commission_bps, req.slippage_bps),
        _bm_returns(),
    )

    # 4. Compute metrics
    ts  = _trade_stats(bt_result["trades"])
    met = _metrics(
        bt_result["daily_returns"],
        req.initial_capital,
        bt_result["final_value"],
        bt_result["equity_curve"],
        bm_rets or None,
    )

    payload: dict = {
        **met,
        **ts,
        "equity_curve":  bt_result["equity_curve"],
        "trades":        bt_result["trades"],
        "parsed_rules":  rules,
        "benchmark":     req.benchmark_symbol,
        "total_costs":   bt_result["total_costs"],
        "commission_bps": req.commission_bps,
        "slippage_bps":  req.slippage_bps,
    }

    # 5. Optional analytics (run in parallel where possible)
    tasks = {}
    if req.run_monte_carlo:
        tasks["mc"] = asyncio.to_thread(
            _monte_carlo,
            bt_result["daily_returns"],
            req.initial_capital,
            req.monte_carlo_sims,
        )
    if req.run_walk_forward:
        tasks["wf"] = asyncio.to_thread(
            _walk_forward, candles, rules, req.initial_capital, 0.7,
            req.commission_bps, req.slippage_bps,
        )
    if req.run_stress_tests:
        tasks["st"] = _stress_tests(req.symbol, rules, req.initial_capital,
                                    req.commission_bps, req.slippage_bps)

    if tasks:
        results_gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), results_gathered):
            if isinstance(result, Exception):
                payload[{"mc": "monte_carlo", "wf": "walk_forward", "st": "stress_tests"}[key]] = {"error": str(result)}
            else:
                payload[{"mc": "monte_carlo", "wf": "walk_forward", "st": "stress_tests"}[key]] = result

    run_id = await _persist_run(
        db, mode="single", req_dict=req.model_dump(), payload=payload, symbol=req.symbol
    )
    payload["simulation_run_id"] = run_id
    return payload


# ── Portfolio simulation endpoint ─────────────────────────────────────────────

@router.post("/run-portfolio")
async def run_portfolio_simulation(req: PortfolioSimulationRequest, db: AsyncSession = Depends(get_db)):
    parse_warnings: list[str] = []
    parsed_holdings_out: list[dict] | None = None

    # Resolve holdings: explicit payload takes priority; fall back to auto-parse
    if req.holdings:
        total_w = sum(h.weight for h in req.holdings)
        if total_w <= 0:
            raise HTTPException(422, "weights must be positive")
        tickers = [h.ticker.upper() for h in req.holdings]
        weights = [h.weight / total_w for h in req.holdings]
        rules = None  # resolved below
    elif req.auto_parse_holdings:
        try:
            parsed = await _parse_strategy_dual(req.strategy_description, req.provider, req.model)
        except Exception as exc:
            raise HTTPException(422, f"Failed to parse strategy: {exc}")

        parse_warnings = parsed["parse_warnings"]
        if req.strict_parse and parse_warnings:
            raise HTTPException(422, f"Strict parse failed: {parse_warnings[0]}")

        if not parsed["holdings"]:
            raise HTTPException(422, "No holdings found in strategy_description and none provided")

        parsed_holdings_out = parsed["holdings"]
        total_alloc = sum(h["allocation_pct"] for h in parsed["holdings"])
        tickers = [h["ticker"] for h in parsed["holdings"]]
        weights = [h["allocation_pct"] / total_alloc for h in parsed["holdings"]]

        # Use parsed trading rules if present, else default allocation-run profile
        tr = parsed.get("trading_rules") or {}
        has_rules = any(tr.get(k) is not None for k in ("buy_pct_drop", "sell_pct_gain", "stop_loss_pct", "hold_days"))
        rules = tr if has_rules else dict(DEFAULT_ALLOCATION_RUN_RULES)
    else:
        raise HTTPException(422, "holdings list is empty and auto_parse_holdings is disabled")

    # 1. Parse strategy rules if not already resolved via dual parser
    if rules is None:
        if req.auto_parse_rules:
            try:
                rules = await _parse_strategy(req.strategy_description, req.provider, req.model)
            except Exception as exc:
                raise HTTPException(422, f"Failed to parse strategy: {exc}")
        else:
            rules = dict(DEFAULT_ALLOCATION_RUN_RULES)

    # 2. Fetch candles for all tickers + benchmark in parallel
    async def _fetch(symbol: str) -> list[dict]:
        return await fmp_service.get_history(symbol, req.start_date, req.end_date)

    all_symbols = tickers + [req.benchmark_symbol]
    fetched = await asyncio.gather(*[_fetch(s) for s in all_symbols], return_exceptions=True)

    candles_per_ticker: list[list[dict]] = []
    for i, ticker in enumerate(tickers):
        result = fetched[i]
        if isinstance(result, Exception) or not result:
            raise HTTPException(404, f"No historical data for {ticker} ({req.start_date}–{req.end_date})")
        candles_per_ticker.append(result)

    bm_candles = fetched[-1]
    bm_rets: list[float] = []
    if not isinstance(bm_candles, Exception) and bm_candles:
        closes = [float(c["close"]) for c in bm_candles]
        bm_rets = [(closes[i] - closes[i-1]) / closes[i-1] if i > 0 else 0.0 for i in range(len(closes))]

    # 3. Run per-leg backtests in parallel threads
    leg_results = await asyncio.gather(*[
        asyncio.to_thread(_run_backtest, candles, rules, req.initial_capital * w,
                          req.commission_bps, req.slippage_bps)
        for candles, w in zip(candles_per_ticker, weights)
    ])

    # 4. Blend into portfolio equity curve
    blended = await asyncio.to_thread(
        _align_portfolio, list(leg_results), tickers, weights, req.initial_capital
    )

    # 5. Compute portfolio-level metrics on the blended curve
    ts_all = {"num_trades": sum(r["num_trades"] for r in [_trade_stats(lr["trades"]) for lr in leg_results]),
               "win_rate": 0.0}
    all_pairs = []
    for lr in leg_results:
        buys  = [t for t in lr["trades"] if t["action"] == "BUY"]
        sells = [t for t in lr["trades"] if t["action"] == "SELL"]
        all_pairs.extend(zip(buys, sells))
    ts_all["win_rate"] = round(sum(1 for b, s in all_pairs if s["price"] > b["price"]) / len(all_pairs), 4) if all_pairs else 0.0

    met = _metrics(
        blended["daily_returns"],
        req.initial_capital,
        blended["final_value"],
        blended["equity_curve"],
        bm_rets or None,
    )

    total_costs = round(sum(lr["total_costs"] for lr in leg_results), 2)
    payload: dict = {
        **met,
        **ts_all,
        "equity_curve":  blended["equity_curve"],
        "trades":        [],    # aggregate trades not meaningful at portfolio level
        "parsed_rules":  rules,
        "benchmark":     req.benchmark_symbol,
        "per_ticker":    blended["per_ticker"],
        "total_costs":   total_costs,
        "commission_bps": req.commission_bps,
        "slippage_bps":  req.slippage_bps,
        "parsed_holdings": parsed_holdings_out,
        "parse_warnings":  parse_warnings,
    }

    # 6. Optional analytics on blended curve
    tasks: dict = {}
    if req.run_monte_carlo:
        tasks["mc"] = asyncio.to_thread(
            _monte_carlo, blended["daily_returns"], req.initial_capital, req.monte_carlo_sims
        )
    if req.run_walk_forward:
        # Walk-forward on the full blended portfolio (each leg split, then blended)
        tasks["wf"] = asyncio.to_thread(
            _portfolio_walk_forward, candles_per_ticker, tickers, weights, rules,
            req.initial_capital, 0.7, req.commission_bps, req.slippage_bps,
        )
    if req.run_stress_tests:
        tasks["st"] = _portfolio_stress_tests(tickers, weights, rules, req.initial_capital,
                                              req.commission_bps, req.slippage_bps)

    if tasks:
        results_gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        key_map = {"mc": "monte_carlo", "wf": "walk_forward", "st": "stress_tests"}
        for key, result in zip(tasks.keys(), results_gathered):
            payload[key_map[key]] = {"error": str(result)} if isinstance(result, Exception) else result

    holdings_list = [{"ticker": t, "weight": w} for t, w in zip(tickers, weights)]
    run_id = await _persist_run(
        db, mode="portfolio", req_dict=req.model_dump(), payload=payload,
        holdings=holdings_list,
        parsed_strategy={"holdings": parsed_holdings_out, "parse_warnings": parse_warnings} if parsed_holdings_out else None,
    )
    payload["simulation_run_id"] = run_id
    return payload


# ── Run history endpoints ─────────────────────────────────────────────────────

@router.get("/runs")
async def list_runs(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """List recent simulation runs (summary fields only, no full curve)."""
    from sqlalchemy import select
    from backend.models import SimulationRun
    result = await db.execute(
        select(SimulationRun).order_by(SimulationRun.created_at.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "mode": r.mode,
            "symbol": r.symbol,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "initial_capital": float(r.initial_capital),
            "benchmark_symbol": r.benchmark_symbol,
            "provider": r.provider,
            "model": r.model,
            **json.loads(r.summary_json),
        }
        for r in rows
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    """Return the full stored payload for a simulation run (sufficient to re-open)."""
    from sqlalchemy import select
    from backend.models import SimulationRun
    result = await db.execute(select(SimulationRun).where(SimulationRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(404, f"Simulation run {run_id} not found")
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat(),
        "mode": run.mode,
        "symbol": run.symbol,
        "holdings": json.loads(run.holdings_json) if run.holdings_json else None,
        "parsed_strategy": json.loads(run.parsed_strategy_json) if run.parsed_strategy_json else None,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "initial_capital": float(run.initial_capital),
        "benchmark_symbol": run.benchmark_symbol,
        "commission_bps": run.commission_bps,
        "slippage_bps": run.slippage_bps,
        "provider": run.provider,
        "model": run.model,
        "request": json.loads(run.request_json),
        "result": json.loads(run.result_json) if run.result_json else None,
    }
