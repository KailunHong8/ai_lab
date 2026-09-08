"""
Canonical StrategyDefinition v1 — the only artifact the backtest engine may execute.

All fields are validated by the compiler before any run. No LLM text reaches the engine.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# Supported v1 indicator kinds
SUPPORTED_INDICATOR_KINDS = {"sma", "ema", "rsi", "rolling_return", "rolling_volatility"}

# Supported predicate operators
SUPPORTED_OPERATORS = {"<", "<=", ">", ">=", "crosses_above", "crosses_below"}


class Instrument(BaseModel):
    ticker: str
    target_weight: Optional[float] = None   # fraction, e.g. 0.10 for 10%
    sector: Optional[str] = None
    rationale: Optional[str] = None


class UniverseSpec(BaseModel):
    instruments: list[Instrument] = Field(default_factory=list)
    benchmark_symbol: str = "SPY"


class DataSpec(BaseModel):
    start_date: str       # YYYY-MM-DD
    end_date: str         # YYYY-MM-DD
    price_basis: Literal["price_return", "total_return"] = "price_return"
    feature_lag_bars: int = Field(default=1, ge=1)   # must be >= 1 (no lookahead)


class IndicatorSpec(BaseModel):
    name: str             # user-given name, e.g. "sma20"
    kind: str             # must be in SUPPORTED_INDICATOR_KINDS
    lookback: int = Field(default=20, gt=0)


class PredicateSpec(BaseModel):
    """A single comparison: left_operand op right_operand."""
    left: str             # indicator name, "close", "open", or numeric literal as string
    op: str               # must be in SUPPORTED_OPERATORS
    right: str            # same options as left


class SignalTreeSpec(BaseModel):
    """all/any tree of predicates. Only one level of grouping supported in v1."""
    logic: Literal["all", "any"] = "all"
    predicates: list[PredicateSpec] = Field(default_factory=list)


class SignalSpec(BaseModel):
    entry: Optional[SignalTreeSpec] = None
    exit: Optional[SignalTreeSpec] = None
    # Legacy four-threshold rules (still supported as the v1 executable subset)
    buy_pct_drop: Optional[float] = None      # positive, e.g. 2.0 means buy on 2% drop
    sell_pct_gain: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    hold_days: Optional[int] = None


class ExecutionSpec(BaseModel):
    signal_time: Literal["close"] = "close"     # signal computed at bar close
    order_delay_bars: int = Field(default=1, ge=1)   # must be >= 1
    fill_price: Literal["next_open"] = "next_open"
    rebalance: Literal["none", "weekly", "monthly"] = "none"


class VolatilityTargetConfig(BaseModel):
    annual_target_vol: float = Field(default=0.15, gt=0.0, le=1.0)
    lookback_bars: int = Field(default=60, gt=0)


class SizingSpec(BaseModel):
    method: Literal["fixed_weights", "volatility_target", "equal_weight"] = "equal_weight"
    vol_target_config: Optional[VolatilityTargetConfig] = None


class CostSpec(BaseModel):
    commission_bps: float = Field(default=2.0, ge=0.0)
    spread_bps: float = Field(default=2.0, ge=0.0)
    base_slippage_bps: float = Field(default=5.0, ge=0.0)
    # ADV-aware slippage (optional)
    adv_slippage_bps_per_1pct: Optional[float] = None    # requires ADV capability
    adv_max_extra_bps: Optional[float] = None


class ConstraintsSpec(BaseModel):
    long_only: bool = True
    max_positions: Optional[int] = None
    max_position_weight: float = Field(default=1.0, gt=0.0, le=1.0)
    cash_reserve: float = Field(default=0.0, ge=0.0, lt=1.0)


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(frozen=False)

    schema_version: Literal[1] = 1
    preset: Optional[str] = None   # e.g. "buy_and_hold"
    universe: UniverseSpec = Field(default_factory=UniverseSpec)
    data: DataSpec
    indicators: list[IndicatorSpec] = Field(default_factory=list)
    signals: SignalSpec = Field(default_factory=SignalSpec)
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    sizing: SizingSpec = Field(default_factory=SizingSpec)
    costs: CostSpec = Field(default_factory=CostSpec)
    constraints: ConstraintsSpec = Field(default_factory=ConstraintsSpec)
    unsupported_intents: list[str] = Field(default_factory=list)

    def definition_hash(self) -> str:
        """SHA-256 of canonical JSON excluding unsupported_intents."""
        d = self.model_dump(exclude={"unsupported_intents", "schema_version"})
        canonical = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()[:24]

    def tickers(self) -> list[str]:
        return [i.ticker for i in self.universe.instruments]


class CompiledPlan(BaseModel):
    """Output of compile_strategy(). Bundles definition + validation findings."""
    definition: StrategyDefinition
    findings: list[dict] = Field(default_factory=list)   # ValidationFinding.model_dump() entries
    is_runnable: bool = False
    warmup_bars: int = 0   # minimum bars needed before first signal
