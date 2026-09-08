# Backtest Strategy Improvement Change Spec

**Date:** 2026-08-01  
**Status:** Proposed  
**Owner:** Quant App  
**Scope:** Backtest engine, validation protocol, experiment tracking, and legacy simulation deprecation path
**Parent:** product_development_roadmap_change_spec.md (standalone track, not a Phase 2 sub-spec)

---

## 1) Summary

Create a dedicated, standalone backtest-improvement track that upgrades strategy simulation realism,
reproducibility, and comparability, while reducing legacy Simulation-page dependency in user flows.

This spec is intentionally outside the Phase 2 Strategy Studio spec so it can be planned, shipped,
and validated independently.

---

## 2) Problem Statement

Current backtesting capability is split between legacy simulation endpoints and Strategy Studio flows.
This causes three issues:

1. Product fragmentation: users can run strategy backtests through different surfaces with different semantics.
2. Validation inconsistency: timeline assumptions, fold protocol, and warning gates are not uniformly enforced.
3. Cleanup risk: legacy paths still power handoffs and parser dependencies, making hard deletion unsafe.

The product needs one credible backtest path with deterministic behavior, explicit assumptions,
reproducible snapshots, and a controlled deprecation plan for legacy simulation UI/entry points.

---

## 3) Goals

1. Establish a single canonical backtest path for strategy execution and reporting.
2. Improve realism for daily-bar simulation without introducing out-of-scope intraday complexity.
3. Enforce reproducible validation with explicit gates and comparable-report rules.
4. Preserve compatibility during migration, then retire legacy simulation entry points safely.
5. Provide audit evidence through tests, run lineage, and deterministic configuration hashes.

---

## 4) Non-Goals

1. Live brokerage execution or autonomous trading.
2. Intraday execution models (order book, impact scheduling, Almgren-Chriss, square-root impact).
3. Derivatives, leverage, shorting, tax-lot accounting, or multi-currency support.
4. Unconstrained parameter optimization or alpha-significance claims.
5. Removing historical compatibility endpoints before migration completion.

---

## 5) Workstream A - Canonical Backtest Runtime

### A1. Runtime contract

Define a single runtime contract consumed by all strategy backtests:

1. Signals computed after bar close at day t.
2. Orders scheduled with configured delay.
3. Fills at next eligible open.
4. Costs applied deterministically (spread/slippage/commission).
5. End-of-day equity marked at selected basis.

### A2. Canonical artifact

Require all strategy runs to execute from a compiled plan artifact and never from free-form
LLM output or ad hoc JSON.

### A3. Output shape

Standardize output payload fields across endpoints:

1. summary metrics
2. equity curve
3. trade log with rejects and costs
4. run metadata (strategy version, snapshot id, protocol hash)

Acceptance:

1. Identical compiled-plan + data-snapshot inputs produce identical outputs.
2. No same-bar signal-fill is possible.

---

## 6) Workstream B - Data Capability and Reproducibility

### B1. Data capability gating

Backtests must validate requested capabilities before execution:

1. price_return vs total_return availability
2. volume coverage for ADV-aware slippage
3. benchmark availability

### B2. Snapshot manifest

Persist a deterministic snapshot manifest for each run including:

1. provider
2. adapter version
3. symbol/date coverage
4. capability flags
5. content hash

Acceptance:

1. Unsupported capabilities block runs with machine-readable errors.
2. No silent fallback from total-return to price-return or ADV-aware to fixed-bps.

---

## 7) Workstream C - Validation Protocol Hardening

### C1. Protocol

Adopt a strict protocol for strategy validation:

1. final untouched holdout
2. rolling chronological folds
3. reproducible seed for stochastic components
4. explicit protocol hash persisted with results

### C2. Guardrails

Add deterministic checks and gates for:

1. insufficient sample windows
2. missing holdout result
3. capability mismatches
4. severe overfit indicators

### C3. Warning acknowledgment

Introduce explicit warning-acknowledgment codes prior to paper-use eligibility status.

Acceptance:

1. Report shows fold results and holdout results separately.
2. Gate status is machine-readable: blocked, review_required, eligible.
3. Acknowledgments are stored with timestamp and user context.

---

## 8) Workstream D - Metrics and Baselines

### D1. Required report metrics

Every strategy report includes:

1. annualized return and volatility
2. Sharpe, Sortino, Calmar
3. max drawdown and average drawdown
4. turnover, total modeled costs, trade count, win rate
5. beta/alpha where benchmark alignment exists

### D2. Baselines

Compute and display baselines on the same snapshot and protocol:

1. cash
2. per-instrument buy-and-hold
3. static initial-weight buy-and-hold portfolio

Acceptance:

1. Baseline and strategy results are directly comparable under shared inputs.
2. Missing comparability is explicitly flagged with reasons.

---

## 9) Workstream E - Legacy Simulation Deprecation

### E1. Migration strategy

Deprecation is phased, not destructive:

1. remove Simulation page from primary navigation
2. route Agent strategy handoff to Strategy Studio draft flow
3. keep legacy simulation APIs temporarily for compatibility
4. remove legacy APIs only after zero active callers and migration sign-off

### E2. Parser dependency removal

Extract parser helpers currently tied to legacy simulation router into a shared service so
Strategy Studio has no runtime dependency on legacy simulation modules.

Acceptance:

1. No first-class UI path depends on legacy Simulation page.
2. Strategy Studio parse/backtest path has no import dependency on legacy simulation router.

---

## 10) API and Contract Changes

1. Maintain compatibility endpoints during migration with explicit legacy labeling.
2. Add/standardize canonical backtest response schema for Strategy Studio endpoints.
3. Add report comparability and gate-status fields required by frontend policy.
4. Add warning acknowledgment payload fields for eligibility transitions.

---

## 11) Test Plan and Evidence

Automated coverage must include:

1. deterministic runtime timing and fill semantics
2. data capability gate failures
3. snapshot hash reproducibility
4. validation fold and holdout separation
5. warning-acknowledgment gate transitions
6. baseline comparability checks
7. legacy-to-canonical migration compatibility contracts

Exit evidence package:

1. test results from fixture-only datasets (no live provider calls)
2. sample run lineage showing strategy version, snapshot hash, protocol hash
3. UI proof that blocked/review-required/eligible states are rendered correctly

---

## 12) Rollout Plan

1. Milestone 1: Canonical runtime and response contract
2. Milestone 2: Capability gates and reproducible snapshots
3. Milestone 3: Validation protocol hardening and warning acknowledgments
4. Milestone 4: Baseline/comparability reporting
5. Milestone 5: UI deprecation of Simulation entry points and Agent handoff migration
6. Milestone 6: Legacy API removal decision gate

---

## 13) Acceptance Criteria

1. The canonical strategy backtest path is reproducible and deterministic.
2. Backtest reports expose assumptions, costs, baselines, and comparability status.
3. Gate outcomes are enforced before paper-use eligibility.
4. Legacy Simulation is no longer a primary user workflow.
5. Migration is reversible until explicit legacy-removal sign-off.
