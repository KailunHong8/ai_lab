"""
Shared analytics library for daily-bar strategy results.

Pure computation — no I/O, no LLM, no project imports.
"""
from __future__ import annotations

import math
from typing import Optional

TRADING_DAYS = 252
RISK_FREE_ANNUAL = 0.05
RISK_FREE_DAILY = RISK_FREE_ANNUAL / TRADING_DAYS


def _safe_std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / (n - 1)
    return math.sqrt(variance)


def sharpe(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - RISK_FREE_DAILY for r in daily_returns]
    std = _safe_std(excess)
    if std == 0:
        return 0.0
    return (sum(excess) / len(excess)) / std * math.sqrt(TRADING_DAYS)


def sortino(daily_returns: list[float]) -> float:
    if len(daily_returns) < 2:
        return 0.0
    excess = [r - RISK_FREE_DAILY for r in daily_returns]
    downside = [r for r in excess if r < 0]
    if not downside:
        return float("inf")
    downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside))
    if downside_std == 0:
        return 0.0
    mean_excess = sum(excess) / len(excess)
    return mean_excess / downside_std * math.sqrt(TRADING_DAYS)


def max_drawdown(equity_curve: list[dict]) -> float:
    """Returns max drawdown as a negative fraction, e.g. -0.35 for 35% drawdown."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]["value"]
    max_dd = 0.0
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        if peak > 0:
            dd = (v - peak) / peak
            if dd < max_dd:
                max_dd = dd
    return max_dd


def avg_drawdown(equity_curve: list[dict]) -> float:
    """Returns mean of all drawdown values as a negative fraction."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]["value"]
    drawdowns: list[float] = []
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        if peak > 0:
            drawdowns.append((v - peak) / peak)
    if not drawdowns:
        return 0.0
    return sum(drawdowns) / len(drawdowns)


def drawdown_series(equity_curve: list[dict]) -> list[float]:
    if not equity_curve:
        return []
    peak = equity_curve[0]["value"]
    result: list[float] = []
    for pt in equity_curve:
        v = pt["value"]
        if v > peak:
            peak = v
        result.append((v - peak) / peak if peak > 0 else 0.0)
    return result


def calmar(daily_returns: list[float], max_dd: float) -> float:
    if max_dd == 0:
        return 0.0
    ann_return = (1 + sum(daily_returns) / max(len(daily_returns), 1)) ** TRADING_DAYS - 1
    return ann_return / abs(max_dd)


def annualized_return(daily_returns: list[float]) -> float:
    if not daily_returns:
        return 0.0
    n = len(daily_returns)
    total = 1.0
    for r in daily_returns:
        total *= (1 + r)
    return total ** (TRADING_DAYS / n) - 1


def annualized_volatility(daily_returns: list[float]) -> float:
    return _safe_std(daily_returns) * math.sqrt(TRADING_DAYS)


def beta_alpha(
    strategy_returns: list[float],
    benchmark_returns: list[float],
) -> tuple[float, float]:
    """Returns (beta, annualized_alpha). Requires aligned series."""
    n = min(len(strategy_returns), len(benchmark_returns))
    if n < 5:
        return (0.0, 0.0)
    sr = strategy_returns[:n]
    br = benchmark_returns[:n]
    b_mean = sum(br) / n
    s_mean = sum(sr) / n
    cov = sum((sr[i] - s_mean) * (br[i] - b_mean) for i in range(n)) / (n - 1)
    b_var = sum((r - b_mean) ** 2 for r in br) / (n - 1)
    if b_var == 0:
        return (0.0, 0.0)
    beta = cov / b_var
    ann_alpha = (s_mean - beta * b_mean) * TRADING_DAYS
    return (beta, ann_alpha)


def win_rate(trades: list[dict]) -> float:
    """Fraction of closed trades that were profitable."""
    closes = [t for t in trades if t.get("pnl") is not None]
    if not closes:
        return 0.0
    wins = sum(1 for t in closes if t["pnl"] > 0)
    return wins / len(closes)


def turnover_annualized(trades: list[dict], equity_curve: list[dict]) -> float:
    """
    Annualized one-way turnover = sum(|trade notionals|) / avg_nav / (years).
    """
    if not trades or not equity_curve:
        return 0.0
    total_notional = sum(abs(t.get("gross_notional", 0)) for t in trades)
    n_days = len(equity_curve)
    avg_nav = sum(pt["value"] for pt in equity_curve) / n_days
    if avg_nav == 0 or n_days == 0:
        return 0.0
    years = n_days / TRADING_DAYS
    return total_notional / avg_nav / max(years, 1 / TRADING_DAYS)


def compute_all(
    daily_returns: list[float],
    equity_curve: list[dict],
    initial_capital: float,
    final_value: float,
    benchmark_returns: Optional[list[float]] = None,
    trades: Optional[list[dict]] = None,
) -> dict:
    """Compute the full scalar metrics dict."""
    max_dd = max_drawdown(equity_curve)
    metrics: dict = {
        "total_return_pct": (final_value - initial_capital) / initial_capital * 100 if initial_capital else 0,
        "annualized_return_pct": annualized_return(daily_returns) * 100,
        "annualized_volatility_pct": annualized_volatility(daily_returns) * 100,
        "sharpe": sharpe(daily_returns),
        "sortino": sortino(daily_returns),
        "max_drawdown_pct": max_dd * 100,
        "avg_drawdown_pct": avg_drawdown(equity_curve) * 100,
        "calmar": calmar(daily_returns, max_dd),
        "sample_bars": len(daily_returns),
    }
    if benchmark_returns:
        b, a = beta_alpha(daily_returns, benchmark_returns)
        metrics["beta"] = b
        metrics["annualized_alpha_pct"] = a * 100
    if trades is not None:
        metrics["trade_count"] = len(trades)
        metrics["win_rate_pct"] = win_rate(trades) * 100
        metrics["turnover_annualized"] = turnover_annualized(trades, equity_curve)
        metrics["total_costs"] = sum(
            t.get("commission", 0) + t.get("slippage_cost", 0) for t in trades
        )
    return metrics
