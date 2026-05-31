"""
Strategy simulation: translate a plain-English strategy into rules via Bedrock,
then replay those rules against FMP historical OHLCV data.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal

import boto3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.services import fmp as fmp_service

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "eu-west-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")

PARSE_SYSTEM = (
    "You are a quantitative strategy parser. "
    "Given a natural-language description of a trading strategy, extract the following JSON fields:\n"
    "  - buy_condition: string description of when to buy (e.g. 'price drops 5% from previous close')\n"
    "  - sell_condition: string description of when to sell (e.g. 'price rises 10% from buy price')\n"
    "  - buy_pct_drop: float | null — percentage drop from previous close that triggers a buy (positive number)\n"
    "  - sell_pct_gain: float | null — percentage gain from buy price that triggers a sell\n"
    "  - stop_loss_pct: float | null — percentage loss from buy price that triggers a stop-loss sell\n"
    "  - hold_days: int | null — maximum holding period in trading days before forced sell\n"
    "Return ONLY a JSON object with these fields. Do not add explanation."
)


def _bedrock_client():
    return boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)


async def _parse_strategy(description: str) -> dict:
    client = _bedrock_client()
    response = client.converse(
        modelId=BEDROCK_MODEL_ID,
        system=[{"text": PARSE_SYSTEM}],
        messages=[{"role": "user", "content": [{"text": description}]}],
    )
    text = response["output"]["message"]["content"][0]["text"]
    # Extract JSON even if the model wraps it in markdown
    start = text.find("{")
    end = text.rfind("}") + 1
    return json.loads(text[start:end])


def _run_backtest(
    candles: list[dict],
    rules: dict,
    initial_capital: float,
) -> dict:
    """
    Simple rule-based replay.
    candles: list of {"date", "open", "high", "low", "close"} sorted oldest-first.
    """
    cash = initial_capital
    shares = 0.0
    buy_price = 0.0
    buy_day = 0
    trades: list[dict] = []
    equity_curve: list[dict] = []

    buy_pct_drop = rules.get("buy_pct_drop")
    sell_pct_gain = rules.get("sell_pct_gain")
    stop_loss_pct = rules.get("stop_loss_pct")
    hold_days = rules.get("hold_days")

    for i, candle in enumerate(candles):
        close = float(candle["close"])
        prev_close = float(candles[i - 1]["close"]) if i > 0 else close

        # Entry signal
        if shares == 0 and buy_pct_drop is not None:
            drop_pct = (prev_close - close) / prev_close * 100
            if drop_pct >= buy_pct_drop and cash > 0:
                shares = cash / close
                buy_price = close
                buy_day = i
                cash = 0.0
                trades.append({"date": candle["date"], "action": "BUY", "price": close})

        # Exit signal
        elif shares > 0:
            gain_pct = (close - buy_price) / buy_price * 100
            loss_pct = (buy_price - close) / buy_price * 100
            days_held = i - buy_day
            should_sell = False

            if sell_pct_gain is not None and gain_pct >= sell_pct_gain:
                should_sell = True
            if stop_loss_pct is not None and loss_pct >= stop_loss_pct:
                should_sell = True
            if hold_days is not None and days_held >= hold_days:
                should_sell = True

            if should_sell:
                cash = shares * close
                trades.append({"date": candle["date"], "action": "SELL", "price": close})
                shares = 0.0

        portfolio_value = cash + shares * close
        equity_curve.append({"date": candle["date"], "value": round(portfolio_value, 2)})

    # Close any open position at last price
    if shares > 0 and candles:
        last_close = float(candles[-1]["close"])
        cash = shares * last_close
        shares = 0.0

    final_value = cash
    pnl = final_value - initial_capital
    pnl_pct = pnl / initial_capital * 100 if initial_capital else 0

    wins = sum(
        1 for j in range(0, len(trades) - 1, 2)
        if trades[j]["action"] == "BUY" and j + 1 < len(trades) and trades[j + 1]["price"] > trades[j]["price"]
    )
    num_trades = len([t for t in trades if t["action"] == "SELL"])
    win_rate = wins / num_trades if num_trades else 0

    # Max drawdown
    peak = initial_capital
    max_dd = 0.0
    for point in equity_curve:
        v = point["value"]
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100 if peak else 0
        if dd > max_dd:
            max_dd = dd

    return {
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "num_trades": num_trades,
        "win_rate": round(win_rate, 4),
        "max_drawdown_pct": round(max_dd, 2),
        "equity_curve": equity_curve,
        "trades": trades,
        "parsed_rules": rules,
    }


class SimulationRequest(BaseModel):
    strategy_description: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float = 10000.0


@router.post("/run")
async def run_simulation(req: SimulationRequest):
    candles = await fmp_service.get_history(req.symbol, req.start_date, req.end_date)
    if not candles:
        raise HTTPException(404, f"No historical data for {req.symbol} in range {req.start_date}–{req.end_date}")

    try:
        rules = await _parse_strategy(req.strategy_description)
    except Exception as exc:
        raise HTTPException(422, f"Failed to parse strategy: {exc}")

    return _run_backtest(candles, rules, req.initial_capital)
