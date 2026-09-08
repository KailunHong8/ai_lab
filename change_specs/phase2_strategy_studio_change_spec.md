# Phase 2 Implementation Spec — Natural-Language Strategy Studio

**Date:** 2026-07-11  
**Status:** Proposed  
**Parent:** [`product_development_roadmap_change_spec.md`](product_development_roadmap_change_spec.md) — Phase 2  
**Assumption:** Phase 1's evidence freshness, simulation-run persistence, decision ledger,
Agent-to-portfolio handoff, and automated regression-test contracts are complete.

## Summary

Build a Strategy Studio that turns a natural-language strategy proposal into a typed,
versioned, user-editable, deterministically compiled daily-bar strategy. A strategy may be
simulated only after it passes static validation. Paper-allocation handoff requires a reviewed
strategy version and a validation report that exposes out-of-sample results, assumptions,
costs, data capability limits, and failed gates.

The Studio is not an alpha generator or institutional execution simulator. It improves the
inspectability and credibility of daily-bar strategy prototyping and educational risk analytics.

## Goals

1. Make every executable strategy an immutable, versioned, inspectable definition.
2. Keep AI limited to proposing a draft; typed backend services validate, compile, and execute it.
3. Replace the current four-threshold, same-close replay semantics with explicit daily-bar
   signal, order, position, and rebalance semantics.
4. Provide rolling chronological validation, a final untouched holdout, relevant baselines,
   and visible tuning history before a strategy can inform a paper allocation.
5. Add realistic daily-bar improvements where supported by a verified data capability:
   volatility-targeted sizing, ADV-aware costs, regime-aware resampling, and total-return data.
6. Let users edit the complete executable definition, compare versions semantically, and
   understand every warning and limitation.
7. Preserve exact inputs, data provenance, compiled configuration, and outputs for every run.

## Non-Goals

1. Live brokerage execution, autonomous trading, or unattended strategy promotion.
2. Intraday data, order-book simulation, execution scheduling, market making, or an
   Almgren-Chriss / square-root market-impact model.
3. Derivatives, leverage, shorting, margin, tax accounting, or multi-currency portfolios.
4. Point-in-time fundamentals, dynamic fundamental screens, or survivorship-bias-free
   historical universes. Phase 2 supports an explicit ticker universe only.
5. Automated parameter search, portfolio optimization, or claims of statistically proven alpha.
6. Replacing the current data providers before a capability assessment requires it.
7. Rewriting Phase 1 contracts or changing the paper-only product boundary.

## Current State (verified 2026-07-11)

- The current parser returns `holdings`, `trading_rules`, `parse_warnings`, and
  `strategy_mode` (`backend/routers/simulation.py`). Its executable rule vocabulary is only
  `buy_pct_drop`, `sell_pct_gain`, `stop_loss_pct`, and `hold_days`.
- Natural-language `buy_condition` and `sell_condition` are stored but not executed.
- The single-ticker engine fills on the signal bar's close, applies fixed commission/slippage,
  and uses all available cash for each entry. Portfolio legs execute independently.
- Input candles contain daily OHLCV. The current FMP/Yahoo history path has no verified
  total-return or corporate-action capability contract.
- Analytics include i.i.d. bootstrap Monte Carlo, a single 70/30 walk-forward split, and
  fixed historical stress windows. They do not include baselines, turnover, a final holdout,
  or reliable portfolio benchmark alignment.
- Phase 1 provides immutable `SimulationRun` records and decisions linked by
  `simulation_run_id`; Phase 2 extends those records rather than duplicating them.
- `Simulation.tsx` can preview parser output but shows executable rules as raw JSON. It has no
  version editor, semantic diff, validation report, or paper-use gate.

## Product and Execution Boundaries

1. Phase 2 is a **daily-bar** simulator. A close-derived signal for day *t* may first fill at
   the open of day *t + 1*, subject to the configured delay. Same-bar signal-and-fill is invalid.
2. An execution is always a modeled fill, never a claim about executable market liquidity.
   Results must retain the daily-bar, model-cost, and data-capability limitations.
3. An explicit ticker universe is the only executable universe in Phase 2. Users may import
   parsed holdings or manually enter tickers and weights; dynamic screening is research context,
   not historical selection logic.
4. A strategy cannot use a data field or risk model that the selected provider adapter has not
   declared available and verified for the requested date range.
5. The current allocation-only parser fallback remains supported as a named `buy_and_hold`
   preset. It becomes a reviewed strategy draft, not an implicit execution shortcut.

## Work Item 1 — Canonical Strategy Definition and Versioning

### 1a. Strategy schema

Create Pydantic models in a dedicated backend strategy package. Store the normalized
definition as versioned JSON and expose the same typed shape through the API.

```text
StrategyDefinition v1
├── metadata
│   ├── name, description, source_prompt, parser_output_json
│   └── schema_version, parent_version_id, created_by, reviewed_at
├── universe
│   └── instruments: [{ticker, target_weight?, sector?, rationale?}]
├── data
│   ├── price_basis: price_return | total_return
│   ├── benchmark_symbol
│   └── feature_lag_bars
├── indicators
│   └── named SMA, EMA, RSI, rolling_return, rolling_volatility definitions
├── signals
│   ├── entry: all/any predicate tree
│   └── exit: all/any predicate tree
├── execution
│   ├── signal_time: close
│   ├── order_delay_bars: integer >= 1
│   ├── fill_price: next_open
│   └── rebalance: none | weekly | monthly
├── sizing
│   └── fixed_weights | volatility_target
├── costs
│   └── commission, spread, base_slippage, optional_adv_slippage
└── constraints
    └── long_only, max_positions, max_position_weight, cash_reserve
```

Supported v1 indicators are SMA, EMA, RSI, rolling return, and rolling volatility over a
positive integer lookback. Supported predicates compare an indicator, close/open price, or
numeric literal using `<`, `<=`, `>`, `>=`, `crosses_above`, and `crosses_below`. A predicate
tree supports `all` / `any` grouping only. Free-form expressions, Python code, and
provider-specific indicator names are rejected.

`feature_lag_bars` defaults to `1`. It may be raised to represent known publication delay but
may never be `0` for data only known at the day's close. `order_delay_bars` defaults to `1`
and may never be less than `1`.

### 1b. Persistence

Add new tables:

```text
Strategy
  id, created_at, name, description, archived_at

StrategyVersion
  id, strategy_id, version_number, created_at, parent_version_id
  source_prompt, parser_output_json, user_edits_json
  definition_json, compiled_plan_json, schema_version
  validation_status: draft | valid | blocked
  definition_hash, reviewed_at, reviewed_by_user

DataSnapshot
  id, created_at, provider, adapter_version, retrieval_at
  manifest_json, content_hash

ValidationReport
  id, strategy_version_id, data_snapshot_id, created_at
  protocol_json, result_json, gate_results_json, status
```

- `StrategyVersion`, `DataSnapshot`, and `ValidationReport` are immutable after creation.
- Editing a draft creates a new version. A reviewed or validated version is never overwritten.
- Add nullable `strategy_version_id`, `data_snapshot_id`, and `validation_report_id` foreign
  keys to Phase 1's `SimulationRun`. A one-time, idempotent SQLite migration script is required
  because existing databases were created before these columns existed. Do not introduce
  Alembic solely for this phase.
- A run based on a Studio strategy must reference all three ids. Legacy free-text runs remain
  supported and are labelled `legacy_unversioned`.

### 1c. Parser-to-schema conversion

- Preserve the existing dual parser as a draft generator. Persist its raw response, provider,
  model, prompt-template version, and parse warnings.
- Deterministically map parsed holdings to `universe.instruments` and the existing
  `DEFAULT_ALLOCATION_RUN_RULES` fallback to the `buy_and_hold` preset.
- The LLM must emit a supported schema candidate or an explicit `unsupported_intent` item.
  Unsupported terms (for example, “buy quality companies,” “trade Fed announcements,” or a
  custom Python indicator) remain visible as non-executable notes and block compilation until
  the user replaces or removes them.
- The compiler, never the LLM, performs ticker normalization, allocation normalization, default
  insertion, numeric bounds checks, and execution-semantics checks.

### Acceptance — Work Item 1

- The same normalized definition produces the same `definition_hash` and compiled plan.
- A user can trace a version to its prompt, raw parser output, edits, parent version, and review.
- A valid Phase 1 parser result can become an editable allocation-only or rule-based draft.
- No executable rule exists outside the v1 schema.

## Work Item 2 — Deterministic Compilation and Static Validation

### 2a. Compile pipeline

Implement this pipeline:

```text
Prompt → parser draft → normalized StrategyDefinition → static validation
      → compiled daily-bar plan → validation run → immutable report → paper-use gate
```

The compiled plan resolves indicator warm-up bars, signal predicates, eligible instruments,
rebalance dates, execution delay, sizing method, cost method, constraints, and required data
capabilities. It is persisted in `StrategyVersion.compiled_plan_json` and is the only strategy
artifact the backtest engine may execute.

Extract the simulation engine, analytics, and parsing helpers from the router into dedicated
services. The router remains responsible for request/response validation only. The existing
four-threshold replay can remain as the compiler target for the legacy-compatible subset, but
new strategy runs must use the compiled plan interpreter.

### 2b. Static validation gates

Return machine-readable findings with `code`, `severity` (`error`, `warning`, `info`), affected
field, and user-facing remediation. Errors block compilation and runs; warnings are recorded in
the version and require explicit user acknowledgement before paper handoff.

| Gate | Outcome |
|---|---|
| Invalid schema, unknown indicator/predicate, malformed ticker, non-positive lookback | Error |
| `feature_lag_bars < 1`, `order_delay_bars < 1`, same-bar fill request | Error |
| Indicator warm-up or requested window insufficient | Error |
| Allocation above 100%, negative weight, violated max weight/position/cash constraint | Error |
| Empty universe, duplicate instrument after normalization, impossible entry/exit configuration | Error |
| Requested total-return or ADV cost without adapter capability | Error |
| Unresolved parse warning or unsupported intent | Error |
| Very short holdout/fold count, high turnover, sparse volume, or fixed-bps fallback | Warning |
| A benchmark unavailable for the selected range | Warning; beta/alpha omitted |

“Likely look-ahead” is an error when a close-derived value can affect a same-day fill. The
compiler must include a deterministic explanation of every feature's availability and order
timing in the plan preview.

### Acceptance — Work Item 2

- Invalid or leakage-prone definitions cannot reach the simulation engine.
- The UI shows the execution timeline and every blocking/warning finding before a run.
- The engine receives only a compiled plan, not LLM text or unvalidated JSON.

## Work Item 3 — Data Capability Adapters and Reproducible Snapshots

### 3a. Adapter contract

Wrap FMP and Yahoo behind a provider-agnostic daily-bar adapter. Each retrieval declares:

```text
DailyBarCapability
  daily_ohlcv
  adjusted_ohlcv_for_total_return
  corporate_action_events
  daily_volume
  adv_lookback_coverage
  provider_terms_reference
```

The adapter returns normalized candles plus a manifest: provider, adapter version, retrieval
timestamp, symbols, inclusive date coverage, available capabilities, requested price basis,
and a content hash of the normalized input. The manifest is stored as `DataSnapshot`.

The system must not infer a capability merely because a provider supplies an `adjusted_close`
field. `total_return` is selectable only when the adapter explicitly verifies a consistent
adjusted OHLC/corporate-action series fit for the strategy's fill semantics.

### 3b. Total return and liquidity-aware costs

- With verified total-return capability, use the adapter's adjusted/corporate-action series for
  both position accounting and fills, and record its adjustment semantics in the snapshot.
- Without it, run only `price_return`, show the limitation in the report and strategy card, and
  reject a `total_return` strategy request.
- Define `ADV20 = mean(close × volume)` across the prior 20 eligible daily bars. ADV-aware
  slippage is available only when this value is valid for every order.
- Use a transparent, bounded linear model:
  `slippage_bps = base_slippage_bps + min(max_extra_bps, bps_per_1pct_adv × order_notional / ADV20 × 100)`.
  Persist every coefficient. If ADV is unavailable, the user may choose fixed bps only; the
  report warns that capacity was not modeled.
- Do not add an intraday impact model or claim capacity estimates from daily bars.

### Acceptance — Work Item 3

- Every Studio run identifies the exact data provider, retrieval, capabilities, and input hash.
- A strategy cannot silently fall back from total return or ADV-aware costs to raw prices/fixed
  costs.
- Re-running from a retained snapshot manifest either produces the same result or reports why
  the source data can no longer be reproduced.

## Work Item 4 — Daily-Bar Execution, Sizing, and Portfolio Constraints

### 4a. Execution model

- Compute signals after the close for bar *t*, submit an order after `order_delay_bars`, and
  fill at the next eligible open. Apply half-spread and slippage adversely to the fill, then
  commission to the notional.
- Mark end-of-day equity at the raw/adjusted close matching the selected price basis.
- Support long-only entry/exit, fixed target weights, no rebalance / weekly / monthly rebalance,
  and explicit cash reserve. Do not support leverage, short positions, pyramiding, or partial
  intraday fills.
- Record each signal, scheduled order, rejected order, fill, cost, and rebalance in the run
  result so users can inspect why the equity curve changed.

### 4b. Sizing

- `fixed_weights`: use reviewed target weights and enforce `max_position_weight`,
  `max_positions`, and cash reserve.
- `volatility_target`: allocate inverse to trailing rolling volatility, subject to the same
  constraints and a user-selected annualized target volatility. It requires enough daily history
  for the declared volatility lookback.
- “Risk budgeting” in Phase 2 means bounded inverse-volatility allocation with explicit
  per-position and portfolio caps. Correlation optimization, marginal contribution to risk, and
  full portfolio optimization remain Phase 3.

### Acceptance — Work Item 4

- The trade log proves a signal cannot fill on its own close bar.
- Runs report turnover, rejected orders, modeled costs, and constraint application.
- Volatility-targeted runs produce reproducible allocations and fail clearly when history is
  insufficient.

## Work Item 5 — Validation Protocol and Daily-Bar Realism Upgrades

### 5a. Validation partitions

Replace the current one-shot 70/30 split with a versioned protocol:

1. Reserve a final untouched holdout (default final 20% of eligible bars; configurable only
   within 15–30%).
2. Split the preceding data into rolling chronological train/test folds. Defaults are
   756 training bars, 126 test bars, and a 63-bar step; windows may be shortened only within
   documented minimum-data constraints.
3. Purge and embargo at least `max(feature lookback, order delay, maximum holding horizon)`
   bars between a training window and its following test window. When no maximum holding horizon
   is declared, the strategy is not eligible for rolling validation.
4. Run the immutable compiled plan separately in each test fold and exactly once on the final
   holdout. The final holdout must not be used by configuration comparison or editing.

The system does not train predictive models in v1. If a future strategy adds learned
preprocessing or parameters, all fitting must occur inside each training fold; Phase 2 rejects
such a strategy until that behavior is implemented.

### 5b. Baselines, metrics, and multiple-testing transparency

Each report includes cash, per-instrument buy-and-hold, and a static initial-weight
buy-and-hold portfolio baseline using the same snapshot, date range, price basis, and modeled
cost policy where applicable. Report annualized return, volatility, Sharpe, Sortino, Calmar,
maximum drawdown, turnover, costs, trade count, win rate, sample bars, benchmark beta/alpha
when aligned, and fold/holdout dispersion.

Record every validation attempt, configuration hash, parent version, and comparable-run count.
The UI must show the number of attempted versions/reports in the strategy lineage and label
unadjusted best-result selection as an overfitting risk. Phase 2 does not claim formal
multiple-testing correction or statistically significant alpha.

### 5c. Regime-aware Monte Carlo

Replace i.i.d. daily-return resampling with a block bootstrap. Classify historical bars into
low/medium/high realized-volatility states using trailing volatility calculated without future
data. Resample contiguous return blocks within the observed state mix, retain a seeded RNG, and
persist the state thresholds, block length, seed, and path count.

Monte Carlo remains a distribution-of-modeled-paths tool, not a forecast. It is unavailable
when there are too few eligible blocks per state; the report records a warning rather than
falling back silently to i.i.d. sampling.

### 5d. Gate outcomes

| Gate | Paper-use outcome |
|---|---|
| Static error or failed compilation | Blocked |
| No final holdout, insufficient folds, or unavailable requested capability | Blocked |
| Final-holdout result unavailable | Blocked |
| Static warnings or adverse validation findings | Review required; user acknowledgement recorded |
| Valid report, completed holdout, acknowledged warnings | Eligible for human-reviewed paper handoff |

“Eligible” does not imply recommendation quality, expected return, or production readiness.
The existing Phase 1 user confirmation is still required for each paper transaction.

### Acceptance — Work Item 5

- Reports clearly separate rolling-fold and untouched-holdout results from in-sample context.
- Purge/embargo length is reproducible and derived from the strategy.
- Baseline, turnover, cost, sample-length, drawdown, and regime-coverage data appear with
  returns.
- Monte Carlo seed and regime/block configuration reproduce the same paths.

## Work Item 6 — Strategy Studio UI and Experiment Management

### User workflow

1. A user opens Strategy Studio and starts from a blank form, a parser draft, or a Phase 1
   agent handoff.
2. The Studio shows the natural-language source alongside a structured, editable rule tree.
3. The user resolves every unsupported intent, parses warnings, and validation error.
4. The user saves a named immutable version, reviews the semantic diff, and confirms it.
5. The user runs the version with a selected data capability and validation protocol.
6. The user reads a strategy card and report before optionally sending the eligible result to
   the existing paper-allocation flow.

### UI requirements

- Add a Strategy Studio route with Draft, Rules, Assumptions & Costs, Validation, Versions,
  and Report views.
- Render only supported schema controls; do not expose raw JSON as the primary editor. An
  advanced read-only JSON view may be available for audit and export.
- Display the exact execution timeline, data snapshot/capability badges, parser/compiler
  findings, and the reason a run or paper handoff is blocked.
- Show an ordered semantic diff grouped by universe, indicators, signals, execution, sizing,
  costs, and constraints; do not use a raw JSON diff as the default experience.
- Support side-by-side report comparisons only when strategy reports share the same data
  snapshot and protocol hash. Otherwise mark them non-comparable and explain which inputs differ.
- Provide a concise strategy card with version, rules, sizing, costs, data basis, validation
  coverage, baselines, fold/holdout results, limitations, and paper-use status.

### Acceptance — Work Item 6

- A user can inspect and edit every executed rule before a run.
- A material edit creates a visible new version and semantic diff.
- The UI does not expose “Run” or “Use for paper trade” as an unqualified success action when
  a blocking gate exists.

## Work Item 7 — APIs and Compatibility

Add typed endpoints under `/api/strategies`:

```text
POST   /api/strategies                         create strategy + initial draft
GET    /api/strategies                         list strategies
GET    /api/strategies/{id}                    read strategy and latest version
POST   /api/strategies/{id}/versions           create version from draft/edit
GET    /api/strategies/{id}/versions/{version} read immutable version
POST   /api/strategies/parse                   parser draft → schema candidate
POST   /api/strategies/validate                static validation + compiled plan preview
POST   /api/strategies/{id}/versions/{version}/validate-run
GET    /api/validation-reports/{id}
GET    /api/strategies/{id}/compare?left=&right=
```

- `validate-run` writes a `DataSnapshot`, `ValidationReport`, and Phase 1 `SimulationRun`.
- Require an explicit `acknowledged_warning_codes` list to move a report from review-required
  to paper-use eligible; persist the acknowledgement and timestamp.
- Keep `/api/simulation/parse-strategy`, `/run`, and `/run-portfolio` for compatibility.
  Label their UI entry points as Legacy Simulation after the Studio is available. They cannot
  generate a Studio paper-use eligibility state.
- The existing Agent action should create a Studio draft when its reply contains a strategy,
  then navigate to that draft. It must not silently run or promote it.

## Test Harness and Acceptance Evidence

### Automated tests

Use the Phase 1 pytest/ASGI harness and fixture-only market data. No test may call an LLM,
FMP, Yahoo, Chroma, Bedrock, or Ollama.

1. **Schema/compiler:** valid strategy canonicalization and hash stability; invalid indicators,
   predicates, timing, weights, and constraints; parser-draft conversion; legacy preset conversion.
2. **Execution:** next-open timing; adverse cost application; rebalance dates; rejected orders;
   fixed and volatility-targeted allocations; deterministic trade/equity logs.
3. **Data adapters:** capability declaration; snapshot manifest/hash; total-return/ADV requests
   rejected when unsupported; no silent fallback.
4. **Validation:** exact fold boundaries, purge/embargo computation, holdout isolation,
   baseline alignment, comparable-report checks, and warning acknowledgements.
5. **Monte Carlo:** seeded block/state resampling produces identical output; insufficient state
   history is reported rather than masked.
6. **Persistence/API:** immutable versions/reports, `SimulationRun` links, migration on an
   existing SQLite fixture, authorization of version/report relationships, and legacy endpoint
   compatibility.
7. **Frontend:** structured edit/save/review flow; semantic diff; blocked run/handoff; warning
   acknowledgement; comparable and non-comparable report views.

### LLM quality evaluation

Create a separate, versioned fixture set of natural-language strategies with expected supported
schema candidates, unsupported intents, and warnings. Evaluate parser-to-schema extraction
offline by provider/model; it is not a deterministic unit test and cannot alter compiler rules.

## Implementation Order

1. Define schema, persistence tables, SQLite migration, parser conversion, and pure compiler
   tests → verify: stable compiled-plan/hash fixtures pass.
2. Extract the daily-bar engine and add static validation/timing semantics → verify:
   same-bar fills are impossible and legacy preset regression tests pass.
3. Add data-adapter capability manifests and snapshots → verify: unsupported total-return/ADV
   requests are blocked with explicit findings.
4. Implement execution, sizing, constraints, costs, and reproducible trade logs → verify:
   deterministic fixture results and cost/turnover tests pass.
5. Replace walk-forward/Monte Carlo and add baselines/holdout reports → verify:
   fold, embargo, holdout, seed, and comparison tests pass.
6. Build Strategy Studio, version diff, report views, Agent draft handoff, and paper-use gate →
   verify: frontend gate tests and manual workflow pass.
7. Run the parser quality fixture evaluation and record results by provider/model → verify:
   unsupported intents are never compiled.
8. Write the user manual after the UI stabilizes → verify: each documented workflow matches an
   acceptance-tested UI path.

## User Manual Deliverable (post-implementation)

Create `docs/strategy_studio_user_manual.md` only after the Studio UI is stable. It must use
the implemented labels and screenshots, and cover:

1. Creating a strategy from a prompt, parser draft, or blank form.
2. Reviewing and editing universe, rules, timing, sizing, costs, and constraints.
3. Understanding parser, compiler, data-capability, and validation findings.
4. Saving/reviewing versions and reading semantic diffs.
5. Running validation and interpreting folds, holdout, baselines, turnover, costs, and Monte
   Carlo without treating them as forecasts.
6. Comparing compatible reports and recognizing non-comparable results.
7. Understanding price-return versus total-return and fixed-cost versus ADV-aware limitations.
8. The exact gate and human confirmation required before paper-allocation handoff.

## Phase 2 Acceptance Criteria

1. The same normalized strategy, data snapshot, and simulation configuration produce
   reproducible results.
2. No strategy reaches the engine with an invalid schema, unavailable data capability, or
   same-bar signal/fill assumption.
3. Users can inspect and edit every executable rule before validation.
4. Each material strategy change creates an immutable version with a readable semantic diff.
5. Every validation report separates rolling chronological tests from the untouched final holdout.
6. Reports include modeled costs, turnover, sample length, drawdown, regime coverage, and
   relevant baselines.
7. Purge/embargo, data capability, total-return, and liquidity limitations are explicit and
   reproducible; unavailable features never degrade silently.
8. Repeated strategy variants and validation attempts are visible in the lineage.
9. A strategy with a blocked validation gate cannot be silently used for a paper-allocation flow.
10. The user manual accurately explains the finalized Studio workflow and its limitations.

## Documentation Updates (on completion, not before)

- `product_note.md`: replace the Strategy Studio and simulator-realism gaps with implemented
  behavior and retained limitations.
- `code_context.md`: document strategy/data/report tables, migration, adapters, compiler,
  validation protocol, APIs, and test commands.
- Add the completed user manual and screenshots under `docs/`.
