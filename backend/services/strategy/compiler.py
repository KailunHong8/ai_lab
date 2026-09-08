"""
Static compiler for StrategyDefinition v1.

No I/O, no LLM. Returns a CompiledPlan with typed findings.
Errors block execution; warnings require user acknowledgement before paper handoff.
"""
from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel

if TYPE_CHECKING:
    from backend.services.strategy.schema import StrategyDefinition, CompiledPlan


class FindingSeverity(str, enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidationFinding(BaseModel):
    severity: FindingSeverity
    code: str
    message: str
    field: Optional[str] = None


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _check_universe(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not defn.universe.instruments:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="UNIVERSE_EMPTY",
            message="Strategy must have at least one instrument in the universe.",
            field="universe.instruments",
        ))
        return findings

    seen: set[str] = set()
    for inst in defn.universe.instruments:
        t = inst.ticker.upper().strip()
        if not t or not t.replace(".", "").replace("-", "").isalnum():
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="INVALID_TICKER",
                message=f"Ticker '{t}' is not a valid symbol.",
                field="universe.instruments",
            ))
        if t in seen:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="DUPLICATE_INSTRUMENT",
                message=f"Ticker '{t}' appears more than once in the universe.",
                field="universe.instruments",
            ))
        seen.add(t)

    # Weight validation for fixed_weights mode
    if defn.sizing.method == "fixed_weights":
        weights = [i.target_weight for i in defn.universe.instruments if i.target_weight is not None]
        if weights:
            total = sum(weights)
            if any(w < 0 for w in weights):
                findings.append(ValidationFinding(
                    severity=FindingSeverity.ERROR,
                    code="NEGATIVE_WEIGHT",
                    message="Negative target weights are not allowed.",
                    field="universe.instruments",
                ))
            if abs(total - 1.0) > 0.02:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.ERROR,
                    code="ALLOCATION_SUM_MISMATCH",
                    message=f"Target weights sum to {total:.3f}, expected ~1.0.",
                    field="universe.instruments",
                ))
            for inst in defn.universe.instruments:
                if inst.target_weight and inst.target_weight > defn.constraints.max_position_weight:
                    findings.append(ValidationFinding(
                        severity=FindingSeverity.ERROR,
                        code="MAX_WEIGHT_EXCEEDED",
                        message=(
                            f"Ticker {inst.ticker} weight {inst.target_weight:.2%} exceeds "
                            f"max_position_weight {defn.constraints.max_position_weight:.2%}."
                        ),
                        field="universe.instruments",
                    ))

    return findings


def _check_dates(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    start = _parse_date(defn.data.start_date)
    end = _parse_date(defn.data.end_date)
    if start is None:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="INVALID_START_DATE",
            message=f"start_date '{defn.data.start_date}' is not a valid YYYY-MM-DD date.",
            field="data.start_date",
        ))
    if end is None:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="INVALID_END_DATE",
            message=f"end_date '{defn.data.end_date}' is not a valid YYYY-MM-DD date.",
            field="data.end_date",
        ))
    if start and end:
        if end <= start:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="DATE_RANGE_INVERTED",
                message="end_date must be after start_date.",
                field="data",
            ))
        elif (end - start).days < 60:
            findings.append(ValidationFinding(
                severity=FindingSeverity.WARNING,
                code="DATE_RANGE_TOO_SHORT",
                message="Date range is shorter than 60 days; validation metrics will be unreliable.",
                field="data",
            ))
    return findings


def _check_indicators(defn: "StrategyDefinition") -> list[ValidationFinding]:
    from backend.services.strategy.schema import SUPPORTED_INDICATOR_KINDS
    findings: list[ValidationFinding] = []
    seen_names: set[str] = set()
    for ind in defn.indicators:
        if ind.kind not in SUPPORTED_INDICATOR_KINDS:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="UNSUPPORTED_INDICATOR",
                message=f"Indicator kind '{ind.kind}' is not supported in v1. Supported: {sorted(SUPPORTED_INDICATOR_KINDS)}.",
                field="indicators",
            ))
        if ind.lookback <= 0:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="INVALID_LOOKBACK",
                message=f"Indicator '{ind.name}' has non-positive lookback {ind.lookback}.",
                field="indicators",
            ))
        if ind.name in seen_names:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="DUPLICATE_INDICATOR_NAME",
                message=f"Indicator name '{ind.name}' is duplicated.",
                field="indicators",
            ))
        seen_names.add(ind.name)
    return findings


def _check_signals(defn: "StrategyDefinition") -> list[ValidationFinding]:
    from backend.services.strategy.schema import SUPPORTED_OPERATORS
    findings: list[ValidationFinding] = []
    signals = defn.signals

    has_entry = (
        signals.buy_pct_drop is not None
        or signals.entry is not None
        or defn.preset == "buy_and_hold"
    )
    if not has_entry:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="NO_ENTRY_SIGNAL",
            message="Strategy has no entry signal. Provide buy_pct_drop or an entry predicate tree.",
            field="signals",
        ))

    # Validate predicate trees
    indicator_names = {ind.name for ind in defn.indicators}
    valid_operands = indicator_names | {"close", "open"}

    for tree_name, tree in [("entry", signals.entry), ("exit", signals.exit)]:
        if tree is None:
            continue
        for pred in tree.predicates:
            if pred.op not in SUPPORTED_OPERATORS:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.ERROR,
                    code="UNSUPPORTED_OPERATOR",
                    message=f"Operator '{pred.op}' in {tree_name} signal is not supported.",
                    field=f"signals.{tree_name}",
                ))
            # left must be a known operand or a numeric literal
            if pred.left not in valid_operands:
                try:
                    float(pred.left)
                except ValueError:
                    findings.append(ValidationFinding(
                        severity=FindingSeverity.ERROR,
                        code="UNKNOWN_OPERAND",
                        message=f"Left operand '{pred.left}' in {tree_name} is not an indicator, 'close', 'open', or a number.",
                        field=f"signals.{tree_name}",
                    ))
            if pred.right not in valid_operands:
                try:
                    float(pred.right)
                except ValueError:
                    findings.append(ValidationFinding(
                        severity=FindingSeverity.ERROR,
                        code="UNKNOWN_OPERAND",
                        message=f"Right operand '{pred.right}' in {tree_name} is not an indicator, 'close', 'open', or a number.",
                        field=f"signals.{tree_name}",
                    ))

    # Unsupported intents block compilation
    if defn.unsupported_intents:
        for intent in defn.unsupported_intents:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="UNSUPPORTED_INTENT",
                message=f"Unsupported intent must be resolved or removed before running: '{intent}'.",
                field="unsupported_intents",
            ))

    return findings


def _check_execution(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    exec_ = defn.execution

    if exec_.order_delay_bars < 1:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="SAME_BAR_FILL",
            message="order_delay_bars must be >= 1. Same-bar signal-and-fill is not allowed.",
            field="execution.order_delay_bars",
        ))
    if defn.data.feature_lag_bars < 1:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="ZERO_FEATURE_LAG",
            message="feature_lag_bars must be >= 1. Using close-derived data on the same bar is look-ahead.",
            field="data.feature_lag_bars",
        ))
    return findings


def _check_sizing(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    sizing = defn.sizing

    if sizing.method == "volatility_target":
        if sizing.vol_target_config is None:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="VOL_TARGET_MISSING",
                message="volatility_target sizing requires vol_target_config to be set.",
                field="sizing.vol_target_config",
            ))
        else:
            # Need enough history for the volatility lookback
            start = _parse_date(defn.data.start_date)
            end = _parse_date(defn.data.end_date)
            lb = sizing.vol_target_config.lookback_bars
            if start and end and (end - start).days < lb * 1.5:
                findings.append(ValidationFinding(
                    severity=FindingSeverity.WARNING,
                    code="INSUFFICIENT_VOL_HISTORY",
                    message=f"Volatility lookback is {lb} bars; date range may be too short.",
                    field="sizing.vol_target_config.lookback_bars",
                ))

    if sizing.method == "fixed_weights":
        missing_weights = [
            i.ticker for i in defn.universe.instruments
            if i.target_weight is None
        ]
        if missing_weights:
            findings.append(ValidationFinding(
                severity=FindingSeverity.ERROR,
                code="MISSING_FIXED_WEIGHT",
                message=f"fixed_weights mode requires target_weight on all instruments. Missing: {missing_weights}.",
                field="universe.instruments",
            ))

    return findings


def _check_costs(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    costs = defn.costs

    if costs.commission_bps < 0 or costs.base_slippage_bps < 0 or costs.spread_bps < 0:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="NEGATIVE_COSTS",
            message="commission_bps, spread_bps, and base_slippage_bps must be >= 0.",
            field="costs",
        ))

    if costs.adv_slippage_bps_per_1pct is not None and costs.adv_max_extra_bps is None:
        findings.append(ValidationFinding(
            severity=FindingSeverity.WARNING,
            code="ADV_MAX_EXTRA_MISSING",
            message="adv_slippage_bps_per_1pct is set but adv_max_extra_bps is not; ADV cost is unbounded.",
            field="costs.adv_max_extra_bps",
        ))

    return findings


def _check_constraints(defn: "StrategyDefinition") -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    c = defn.constraints

    if c.max_position_weight <= 0 or c.max_position_weight > 1.0:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="INVALID_MAX_WEIGHT",
            message="max_position_weight must be in (0, 1].",
            field="constraints.max_position_weight",
        ))
    if c.cash_reserve < 0 or c.cash_reserve >= 1.0:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="INVALID_CASH_RESERVE",
            message="cash_reserve must be in [0, 1).",
            field="constraints.cash_reserve",
        ))
    if c.max_positions is not None and c.max_positions < 1:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="INVALID_MAX_POSITIONS",
            message="max_positions must be >= 1 if set.",
            field="constraints.max_positions",
        ))
    if not c.long_only:
        findings.append(ValidationFinding(
            severity=FindingSeverity.ERROR,
            code="SHORT_NOT_SUPPORTED",
            message="Short positions are not supported in Phase 2. long_only must be true.",
            field="constraints.long_only",
        ))
    return findings


def compile_strategy(defn: "StrategyDefinition") -> "CompiledPlan":
    """
    Run all static checks. Returns CompiledPlan with findings and is_runnable flag.
    No I/O. Deterministic.
    """
    # Lazy import to avoid circular at module load
    from backend.services.strategy.schema import CompiledPlan

    findings: list[ValidationFinding] = []
    findings += _check_universe(defn)
    findings += _check_dates(defn)
    findings += _check_indicators(defn)
    findings += _check_signals(defn)
    findings += _check_execution(defn)
    findings += _check_sizing(defn)
    findings += _check_costs(defn)
    findings += _check_constraints(defn)

    is_runnable = not any(f.severity == FindingSeverity.ERROR for f in findings)

    # Compute warmup bars = max indicator lookback (0 if none)
    warmup_bars = max((ind.lookback for ind in defn.indicators), default=0)

    return CompiledPlan(
        definition=defn,
        findings=[f.model_dump() for f in findings],
        is_runnable=is_runnable,
        warmup_bars=warmup_bars,
    )
