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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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

# Historical date ranges for stress-test overlays
STRESS_PERIODS = {
    "2008_gfc":       ("2008-01-01", "2009-06-30", "2008 GFC"),
    "2020_covid":     ("2020-02-01", "2020-12-31", "2020 COVID"),
    "2022_rate_shock":("2022-01-01", "2022-12-31", "2022 Rate Shock"),
}


# ── LLM parsing (provider-agnostic) ──────────────────────────────────────────

async def _parse_strategy(description: str, provider: str, model: Optional[str]) -> dict:
    if provider == "ollama":
        from backend.services import ollama_client
        _model = model or ollama_client.OLLAMA_DEFAULT_MODEL
        result = await ollama_client.extract_json(description, PARSE_SYSTEM, model=_model)
        if result and result != {"theses": [], "relationships": []}:
            return result
        raise ValueError("Ollama returned no parseable strategy JSON")
    else:
        import boto3
        region = os.getenv("BEDROCK_REGION", "eu-west-1")
        model_id = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
        client = boto3.client("bedrock-runtime", region_name=region)
        resp = client.converse(
            modelId=model_id,
            system=[{"text": PARSE_SYSTEM}],
            messages=[{"role": "user", "content": [{"text": description}]}],
        )
        text = resp["output"]["message"]["content"][0]["text"]
        start, end = text.find("{"), text.rfind("}") + 1
        return json.loads(text[start:end])


# ── Core backtest engine ──────────────────────────────────────────────────────

def _run_backtest(candles: list[dict], rules: dict, initial_capital: float) -> dict:
    """
    Rule-based replay. Returns equity curve, trades, and raw return series.
    candles sorted oldest-first: [{"date", "open", "high", "low", "close"}, ...]
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

    prev_portfolio = initial_capital

    for i, candle in enumerate(candles):
        close      = float(candle["close"])
        prev_close = float(candles[i - 1]["close"]) if i > 0 else close

        if shares == 0 and buy_pct_drop is not None:
            drop = (prev_close - close) / prev_close * 100
            if drop >= buy_pct_drop and cash > 0:
                shares    = cash / close
                buy_price = close
                buy_day   = i
                cash      = 0.0
                trades.append({"date": candle["date"], "action": "BUY", "price": close})

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
                cash   = shares * close
                shares = 0.0
                trades.append({"date": candle["date"], "action": "SELL", "price": close})

        portfolio_value = cash + shares * close
        equity_curve.append({"date": candle["date"], "value": round(portfolio_value, 2)})

        ret = (portfolio_value - prev_portfolio) / prev_portfolio if prev_portfolio else 0.0
        daily_returns.append(ret)
        prev_portfolio = portfolio_value

    if shares > 0 and candles:
        cash   = shares * float(candles[-1]["close"])
        shares = 0.0

    return {"equity_curve": equity_curve, "trades": trades, "daily_returns": daily_returns, "final_value": cash}


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
    horizon_days: int | None = None,
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

    is_res  = _run_backtest(is_candles,  rules, initial_capital)
    oos_res = _run_backtest(oos_candles, rules, initial_capital)

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


# ── Stress tests ──────────────────────────────────────────────────────────────

async def _stress_tests(symbol: str, rules: dict, initial_capital: float) -> list[dict]:
    """Run the strategy over known crash/stress periods."""
    results = []
    for key, (start, end, label) in STRESS_PERIODS.items():
        candles = await fmp_service.get_history(symbol, start, end)
        if len(candles) < 10:
            results.append({"period": label, "error": "insufficient data"})
            continue
        res = _run_backtest(candles, rules, initial_capital)
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


# ── Request / response models ─────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    strategy_description: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000.0
    provider: str = "bedrock"          # "bedrock" or "ollama"
    model: Optional[str] = None
    run_monte_carlo: bool = True
    monte_carlo_sims: int = 300
    run_walk_forward: bool = True
    run_stress_tests: bool = True
    benchmark_symbol: str = "SPY"


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post("/run")
async def run_simulation(req: SimulationRequest):
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
        asyncio.to_thread(_run_backtest, candles, rules, req.initial_capital),
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
            _walk_forward, candles, rules, req.initial_capital
        )
    if req.run_stress_tests:
        tasks["st"] = _stress_tests(req.symbol, rules, req.initial_capital)

    if tasks:
        results_gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for key, result in zip(tasks.keys(), results_gathered):
            if isinstance(result, Exception):
                payload[{"mc": "monte_carlo", "wf": "walk_forward", "st": "stress_tests"}[key]] = {"error": str(result)}
            else:
                payload[{"mc": "monte_carlo", "wf": "walk_forward", "st": "stress_tests"}[key]] = result

    return payload
