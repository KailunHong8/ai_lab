"""
Bridge: convert the legacy parser output (holdings + trading_rules) into a StrategyDefinition.

No LLM call here — pure transformation.
"""
from __future__ import annotations

from backend.services.strategy.schema import (
    StrategyDefinition,
    UniverseSpec,
    DataSpec,
    Instrument,
    SignalSpec,
    ExecutionSpec,
    SizingSpec,
    CostSpec,
    ConstraintsSpec,
)


def legacy_to_strategy_definition(
    parsed: dict,
    start_date: str,
    end_date: str,
    benchmark: str = "SPY",
    commission_bps: float = 2.0,
    slippage_bps: float = 5.0,
) -> StrategyDefinition:
    """
    Convert output of simulation._parse_strategy_dual() into a StrategyDefinition draft.

    parsed keys:
      holdings: [{ticker, allocation_pct, ...}]
      trading_rules: {buy_pct_drop, sell_pct_gain, stop_loss_pct, hold_days, buy_condition, sell_condition}
      strategy_mode: "allocation_only" | "rules_only" | "allocation_and_rules"
      parse_warnings: [str]
    """
    holdings_raw = parsed.get("holdings") or []
    trading_rules = parsed.get("trading_rules") or {}
    strategy_mode = parsed.get("strategy_mode", "allocation_only")

    # Build instruments list
    instruments: list[Instrument] = []
    total_alloc = sum(
        float(h.get("allocation_pct") or 0) for h in holdings_raw
    )
    for h in holdings_raw:
        ticker = str(h.get("ticker", "")).upper().strip()
        if not ticker:
            continue
        alloc_pct = float(h.get("allocation_pct") or 0)
        weight = alloc_pct / 100.0 if total_alloc > 0 else None
        instruments.append(Instrument(
            ticker=ticker,
            target_weight=round(weight, 6) if weight is not None else None,
            sector=h.get("sector"),
            rationale=h.get("rationale"),
        ))

    universe = UniverseSpec(instruments=instruments, benchmark_symbol=benchmark)

    # Sizing
    has_weights = any(i.target_weight is not None for i in instruments)
    if strategy_mode in ("allocation_only", "allocation_and_rules") and has_weights:
        sizing_method = "fixed_weights"
    elif len(instruments) > 1:
        sizing_method = "equal_weight"
    else:
        sizing_method = "equal_weight"

    # Signals
    buy_pct_drop = trading_rules.get("buy_pct_drop")
    sell_pct_gain = trading_rules.get("sell_pct_gain")
    stop_loss_pct = trading_rules.get("stop_loss_pct")
    hold_days = trading_rules.get("hold_days")

    # Unsupported intents: store free-text conditions as non-executable notes
    unsupported_intents: list[str] = []
    buy_condition = trading_rules.get("buy_condition")
    sell_condition = trading_rules.get("sell_condition")
    if buy_condition and buy_pct_drop is None:
        unsupported_intents.append(f"buy_condition: {buy_condition}")
    if sell_condition and sell_pct_gain is None and stop_loss_pct is None:
        unsupported_intents.append(f"sell_condition: {sell_condition}")

    # Preset detection
    preset = None
    is_buy_and_hold = (
        buy_pct_drop is not None and buy_pct_drop == 0.0
        and sell_pct_gain is None
        and stop_loss_pct is None
        and hold_days is None
        and strategy_mode == "allocation_only"
    )
    if is_buy_and_hold or strategy_mode == "allocation_only":
        preset = "buy_and_hold"
        # Clear unsupported intents for pure allocation strategies
        unsupported_intents = []

    return StrategyDefinition(
        universe=universe,
        data=DataSpec(
            start_date=start_date,
            end_date=end_date,
            price_basis="price_return",
        ),
        signals=SignalSpec(
            buy_pct_drop=float(buy_pct_drop) if buy_pct_drop is not None else None,
            sell_pct_gain=float(sell_pct_gain) if sell_pct_gain is not None else None,
            stop_loss_pct=float(stop_loss_pct) if stop_loss_pct is not None else None,
            hold_days=int(hold_days) if hold_days is not None else None,
        ),
        execution=ExecutionSpec(order_delay_bars=1),
        sizing=SizingSpec(method=sizing_method),
        costs=CostSpec(
            commission_bps=commission_bps,
            base_slippage_bps=slippage_bps,
        ),
        constraints=ConstraintsSpec(long_only=True),
        unsupported_intents=unsupported_intents,
        preset=preset,
    )
