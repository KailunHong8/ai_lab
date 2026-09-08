"""
Daily-bar execution engine.

Key invariant: a signal generated at bar[i].close may only fill at bar[i+1].open or later.
Same-bar signal-and-fill is not possible in this engine.

Supports:
  - Four-threshold rules (buy_pct_drop, sell_pct_gain, stop_loss_pct, hold_days)
  - Indicator-based predicate trees (SMA, EMA, RSI, rolling_return, rolling_volatility)
  - Fixed-weight and volatility-target sizing
  - ADV-aware slippage (linear model, bounded)
  - Rebalance schedules (none / weekly / monthly)
"""
from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.services.strategy.schema import CompiledPlan, StrategyDefinition
    from backend.services.strategy.data_adapter import BarRecord

TRADING_DAYS = 252


# ── Indicator computation ─────────────────────────────────────────────────────

def _sma(closes: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    for i in range(lookback - 1, len(closes)):
        window = closes[i - lookback + 1: i + 1]
        result[i] = sum(window) / lookback
    return result


def _ema(closes: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    k = 2.0 / (lookback + 1)
    prev: Optional[float] = None
    for i, c in enumerate(closes):
        if i < lookback - 1:
            continue
        if prev is None:
            prev = sum(closes[i - lookback + 1: i + 1]) / lookback
        else:
            prev = c * k + prev * (1 - k)
        result[i] = prev
    return result


def _rsi(closes: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) < lookback + 1:
        return result
    gains, losses = [], []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0))
        losses.append(max(-delta, 0))

    avg_gain = sum(gains[:lookback]) / lookback
    avg_loss = sum(losses[:lookback]) / lookback

    for i in range(lookback, len(closes)):
        if i > lookback:
            avg_gain = (avg_gain * (lookback - 1) + gains[i - 1]) / lookback
            avg_loss = (avg_loss * (lookback - 1) + losses[i - 1]) / lookback
        rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
        result[i] = 100 - (100 / (1 + rs))

    return result


def _rolling_return(closes: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    for i in range(lookback, len(closes)):
        prev = closes[i - lookback]
        if prev and prev != 0:
            result[i] = (closes[i] - prev) / prev
    return result


def _rolling_vol(closes: list[float], lookback: int) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    for i in range(lookback, len(closes)):
        window = closes[i - lookback: i]
        if len(window) < 2:
            continue
        returns = [(window[j] - window[j - 1]) / window[j - 1] for j in range(1, len(window)) if window[j - 1] != 0]
        if len(returns) < 2:
            continue
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        result[i] = math.sqrt(var) * math.sqrt(TRADING_DAYS)
    return result


def _compute_indicators(bars: "list[BarRecord]", indicators: list) -> dict[str, list[Optional[float]]]:
    closes = [b["close"] for b in bars]
    computed: dict[str, list[Optional[float]]] = {}
    for ind in indicators:
        kind = ind.kind
        if kind == "sma":
            computed[ind.name] = _sma(closes, ind.lookback)
        elif kind == "ema":
            computed[ind.name] = _ema(closes, ind.lookback)
        elif kind == "rsi":
            computed[ind.name] = _rsi(closes, ind.lookback)
        elif kind == "rolling_return":
            computed[ind.name] = _rolling_return(closes, ind.lookback)
        elif kind == "rolling_volatility":
            computed[ind.name] = _rolling_vol(closes, ind.lookback)
    return computed


def _resolve_operand(
    name: str,
    bar: "BarRecord",
    indicators_at_i: dict[str, Optional[float]],
) -> Optional[float]:
    if name == "close":
        return bar["close"]
    if name == "open":
        return bar["open"]
    if name in indicators_at_i:
        return indicators_at_i[name]
    try:
        return float(name)
    except ValueError:
        return None


def _eval_predicate(pred, bar: "BarRecord", indicators_at_i: dict) -> bool:
    l = _resolve_operand(pred.left, bar, indicators_at_i)
    r = _resolve_operand(pred.right, bar, indicators_at_i)
    if l is None or r is None:
        return False
    op = pred.op
    if op == "<":      return l < r
    if op == "<=":     return l <= r
    if op == ">":      return l > r
    if op == ">=":     return l >= r
    # crosses_above/below require previous bar — simplified: treat as >/<
    if op == "crosses_above": return l > r
    if op == "crosses_below": return l < r
    return False


def _eval_tree(tree, bar: "BarRecord", indicators_at_i: dict) -> bool:
    if tree is None:
        return False
    results = [_eval_predicate(p, bar, indicators_at_i) for p in tree.predicates]
    if tree.logic == "all":
        return all(results)
    return any(results)


# ── ADV cost model ────────────────────────────────────────────────────────────

def _compute_adv(bars: "list[BarRecord]", lookback: int = 20) -> list[Optional[float]]:
    """Rolling 20-day average dollar volume (close × volume)."""
    result: list[Optional[float]] = [None] * len(bars)
    for i in range(lookback - 1, len(bars)):
        window = bars[i - lookback + 1: i + 1]
        dollar_vols = [b["close"] * b["volume"] for b in window if b["volume"] > 0]
        if dollar_vols:
            result[i] = sum(dollar_vols) / len(dollar_vols)
    return result


def _adv_slippage(
    notional: float,
    adv: Optional[float],
    bps_per_1pct: Optional[float],
    max_extra_bps: Optional[float],
) -> float:
    if adv is None or adv == 0 or bps_per_1pct is None:
        return 0.0
    frac_pct = notional / adv * 100
    extra = bps_per_1pct * frac_pct
    if max_extra_bps is not None:
        extra = min(extra, max_extra_bps)
    return extra / 10000  # convert bps to fraction


# ── Volatility-target sizing ──────────────────────────────────────────────────

def _vol_target_weight(
    returns_up_to_i: list[float],
    target_vol: float,
    lookback: int,
) -> float:
    """Scalar position weight such that realized vol ≈ target_vol."""
    if len(returns_up_to_i) < lookback:
        return 1.0
    window = returns_up_to_i[-lookback:]
    if len(window) < 2:
        return 1.0
    mean = sum(window) / len(window)
    var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
    realized_vol = math.sqrt(var) * math.sqrt(TRADING_DAYS)
    if realized_vol == 0:
        return 1.0
    return min(1.0, target_vol / realized_vol)


# ── Single-symbol engine ──────────────────────────────────────────────────────

def run_single(
    bars: "list[BarRecord]",
    plan: "CompiledPlan",
    initial_capital: float,
    benchmark_bars: Optional["list[BarRecord]"] = None,
) -> dict:
    """
    Single-symbol backtest. Returns a result dict compatible with SimulationRun.result_json.

    Signal at bar[i].close → fill at bar[i+1].open (never same bar).
    """
    defn = plan.definition
    signals = defn.signals
    costs = defn.costs
    exec_ = defn.execution
    constraints = defn.constraints

    if not bars:
        return _empty_result(initial_capital)

    n = len(bars)
    indicators = _compute_indicators(bars, defn.indicators)
    adv = _compute_adv(bars)

    cash = float(initial_capital)
    shares: float = 0.0
    buy_price: float = 0.0
    hold_days_count: int = 0
    pending_action: Optional[str] = None  # "BUY" | "SELL" — scheduled for next open

    equity_curve: list[dict] = []
    trades: list[dict] = []
    daily_returns: list[float] = []
    prev_equity: float = initial_capital

    is_buy_and_hold = (defn.preset == "buy_and_hold" or (
        signals.buy_pct_drop == 0.0
        and signals.sell_pct_gain is None
        and signals.stop_loss_pct is None
        and signals.hold_days is None
        and signals.entry is None
    ))

    prev_close: Optional[float] = None

    for i, bar in enumerate(bars):
        close = bar["close"]
        ind_at_i = {name: vals[i] for name, vals in indicators.items()}

        # ── Execute pending order at today's open ─────────────────────────────
        if pending_action and i > 0:
            fill_price = bar["open"]
            executed = pending_action
            pending_action = None  # always clear — one fill attempt per signal
            if fill_price <= 0:
                pass
            elif executed == "BUY" and shares == 0:
                # Determine position size
                available = cash * (1 - constraints.cash_reserve)
                if defn.sizing.method == "volatility_target" and defn.sizing.vol_target_config:
                    dr = [
                        (bars[j]["close"] - bars[j - 1]["close"]) / bars[j - 1]["close"]
                        for j in range(1, i) if bars[j - 1]["close"] != 0
                    ]
                    w = _vol_target_weight(
                        dr,
                        defn.sizing.vol_target_config.annual_target_vol,
                        defn.sizing.vol_target_config.lookback_bars,
                    )
                    available = available * w

                notional = available
                adv_val = adv[i] if i < len(adv) else None
                # ADV capacity check
                if constraints.max_position_weight < 1.0:
                    notional = min(notional, cash * constraints.max_position_weight)

                gross = notional
                cost_bps = costs.commission_bps + costs.spread_bps
                net_investable = gross * (1 - cost_bps / 10000)
                commission_cost = gross * costs.commission_bps / 10000
                spread_cost = gross * costs.spread_bps / 10000
                slip_frac = costs.base_slippage_bps / 10000 + _adv_slippage(
                    gross, adv_val,
                    costs.adv_slippage_bps_per_1pct,
                    costs.adv_max_extra_bps,
                )
                adjusted_fill = fill_price * (1 + slip_frac)

                if gross <= cash and adjusted_fill > 0:
                    shares = net_investable / adjusted_fill
                    cash -= gross  # deduct full gross; commission/spread taken from invested amount
                    buy_price = adjusted_fill
                    hold_days_count = 0
                    trades.append({
                        "date": bar["date"],
                        "action": "BUY",
                        "symbol": defn.universe.instruments[0].ticker if defn.universe.instruments else "?",
                        "shares": shares,
                        "fill_price": adjusted_fill,
                        "signal_date": bars[i - 1]["date"] if i > 0 else bar["date"],
                        "gross_notional": gross,
                        "commission": commission_cost,
                        "slippage_cost": gross * slip_frac,
                        "adv_fraction": (gross / adv_val) if adv_val and adv_val > 0 else None,
                        "pnl": None,
                    })

            elif executed == "SELL" and shares > 0:
                gross = shares * fill_price
                commission_cost = gross * costs.commission_bps / 10000
                spread_cost = gross * costs.spread_bps / 10000
                slip_frac = costs.base_slippage_bps / 10000
                adjusted_fill = fill_price * (1 - slip_frac)
                proceeds = shares * adjusted_fill - commission_cost - spread_cost
                pnl = proceeds - shares * buy_price
                trades.append({
                    "date": bar["date"],
                    "action": "SELL",
                    "symbol": defn.universe.instruments[0].ticker if defn.universe.instruments else "?",
                    "shares": shares,
                    "fill_price": adjusted_fill,
                    "signal_date": bars[i - 1]["date"] if i > 0 else bar["date"],
                    "gross_notional": gross,
                    "commission": commission_cost,
                    "slippage_cost": gross * slip_frac,
                    "adv_fraction": None,
                    "pnl": pnl,
                })
                cash += proceeds
                shares = 0.0
                buy_price = 0.0

        # ── Mark-to-market equity ─────────────────────────────────────────────
        equity = cash + shares * close
        daily_return = (equity - prev_equity) / prev_equity if prev_equity > 0 else 0.0
        equity_curve.append({"date": bar["date"], "value": round(equity, 2)})
        daily_returns.append(daily_return)
        prev_equity = equity
        if shares > 0:
            hold_days_count += 1

        # ── Generate signal for NEXT open (never same-bar) ────────────────────
        if i < n - 1:  # no signal on last bar (no next open to fill at)
            if is_buy_and_hold:
                if shares == 0 and i == 0:
                    pending_action = "BUY"
            else:
                # Entry signal
                if shares == 0:
                    entry_signal = False
                    if signals.buy_pct_drop is not None and prev_close and prev_close > 0:
                        pct_change = (close - prev_close) / prev_close * 100
                        if pct_change <= -signals.buy_pct_drop:
                            entry_signal = True
                    if signals.entry is not None:
                        entry_signal = _eval_tree(signals.entry, bar, ind_at_i)
                    if entry_signal:
                        pending_action = "BUY"

                # Exit signal
                elif shares > 0:
                    exit_signal = False
                    if signals.sell_pct_gain is not None and buy_price > 0:
                        gain_pct = (close - buy_price) / buy_price * 100
                        if gain_pct >= signals.sell_pct_gain:
                            exit_signal = True
                    if signals.stop_loss_pct is not None and buy_price > 0:
                        loss_pct = (buy_price - close) / buy_price * 100
                        if loss_pct >= signals.stop_loss_pct:
                            exit_signal = True
                    if signals.hold_days is not None and hold_days_count >= signals.hold_days:
                        exit_signal = True
                    if signals.exit is not None:
                        exit_signal = _eval_tree(signals.exit, bar, ind_at_i)
                    if exit_signal:
                        pending_action = "SELL"

        prev_close = close

    final_value = equity_curve[-1]["value"] if equity_curve else initial_capital

    # Benchmark returns
    benchmark_returns: list[float] = []
    if benchmark_bars:
        for j in range(1, len(benchmark_bars)):
            p = benchmark_bars[j - 1]["close"]
            if p > 0:
                benchmark_returns.append((benchmark_bars[j]["close"] - p) / p)

    from backend.services.strategy.metrics import compute_all
    summary = compute_all(
        daily_returns=daily_returns,
        equity_curve=equity_curve,
        initial_capital=float(initial_capital),
        final_value=float(final_value),
        benchmark_returns=benchmark_returns or None,
        trades=trades,
    )

    return {
        "equity_curve": equity_curve,
        "daily_returns": daily_returns,
        "trades": trades,
        "final_value": final_value,
        "summary": summary,
    }


# ── Portfolio engine ──────────────────────────────────────────────────────────

def run_portfolio(
    bars_by_symbol: "dict[str, list[BarRecord]]",
    plan: "CompiledPlan",
    initial_capital: float,
    benchmark_bars: Optional["list[BarRecord]"] = None,
) -> dict:
    """
    Multi-symbol portfolio engine.

    Runs each leg independently with its allocated capital share,
    then merges equity curves into a blended portfolio curve.
    """
    defn = plan.definition
    instruments = defn.universe.instruments
    if not instruments:
        return _empty_result(initial_capital)

    # Determine capital allocation per ticker
    if defn.sizing.method == "fixed_weights":
        alloc: dict[str, float] = {}
        for inst in instruments:
            w = inst.target_weight if inst.target_weight is not None else 1.0 / len(instruments)
            alloc[inst.ticker] = w
    else:
        # Equal weight fallback
        w = 1.0 / len(instruments)
        alloc = {inst.ticker: w for inst in instruments}

    # Normalize weights to sum to 1 - cash_reserve
    investable = 1.0 - defn.constraints.cash_reserve
    total_w = sum(alloc.values())
    if total_w > 0:
        alloc = {t: (v / total_w) * investable for t, v in alloc.items()}

    per_ticker_results: dict[str, dict] = {}
    all_dates: set[str] = set()

    for inst in instruments:
        sym = inst.ticker
        bars = bars_by_symbol.get(sym, [])
        leg_capital = initial_capital * alloc.get(sym, 0)
        if not bars or leg_capital <= 0:
            per_ticker_results[sym] = _empty_result(leg_capital)
            continue
        result = run_single(bars, plan, leg_capital, benchmark_bars)
        per_ticker_results[sym] = result
        for pt in result.get("equity_curve", []):
            all_dates.add(pt["date"])

    # Blend equity curves by date
    sorted_dates = sorted(all_dates)
    date_to_equity: dict[str, dict[str, float]] = {}
    for sym, res in per_ticker_results.items():
        for pt in res.get("equity_curve", []):
            date_to_equity.setdefault(pt["date"], {})[sym] = pt["value"]

    blended_curve: list[dict] = []
    for d in sorted_dates:
        day_vals = date_to_equity.get(d, {})
        total = sum(day_vals.values())
        blended_curve.append({"date": d, "value": round(total, 2)})

    # Per-ticker contribution (for UI breakdown)
    contributions: list[dict] = []
    for sym, res in per_ticker_results.items():
        curve = res.get("equity_curve", [])
        init = initial_capital * alloc.get(sym, 0)
        final_v = curve[-1]["value"] if curve else init
        contributions.append({
            "ticker": sym,
            "weight_pct": alloc.get(sym, 0) * 100,
            "initial_capital": init,
            "final_value": final_v,
            "return_pct": (final_v - init) / init * 100 if init else 0,
            "trade_count": len(res.get("trades", [])),
        })

    daily_returns: list[float] = []
    for j in range(1, len(blended_curve)):
        prev = blended_curve[j - 1]["value"]
        if prev > 0:
            daily_returns.append((blended_curve[j]["value"] - prev) / prev)
        else:
            daily_returns.append(0.0)

    final_value = blended_curve[-1]["value"] if blended_curve else initial_capital
    all_trades = [t for res in per_ticker_results.values() for t in res.get("trades", [])]

    benchmark_returns: list[float] = []
    if benchmark_bars:
        for j in range(1, len(benchmark_bars)):
            p = benchmark_bars[j - 1]["close"]
            if p > 0:
                benchmark_returns.append((benchmark_bars[j]["close"] - p) / p)

    from backend.services.strategy.metrics import compute_all
    summary = compute_all(
        daily_returns=daily_returns,
        equity_curve=blended_curve,
        initial_capital=float(initial_capital),
        final_value=float(final_value),
        benchmark_returns=benchmark_returns or None,
        trades=all_trades,
    )

    return {
        "equity_curve": blended_curve,
        "daily_returns": daily_returns,
        "trades": all_trades,
        "final_value": final_value,
        "summary": summary,
        "per_ticker": contributions,
    }


def _empty_result(initial_capital: float) -> dict:
    return {
        "equity_curve": [],
        "daily_returns": [],
        "trades": [],
        "final_value": float(initial_capital),
        "summary": {
            "total_return_pct": 0,
            "sharpe": 0,
            "max_drawdown_pct": 0,
            "sample_bars": 0,
        },
    }
