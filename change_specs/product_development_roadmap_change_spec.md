# Product Development Roadmap Change Spec

**Date:** 2026-07-11  
**Status:** Proposed  
**Scope:** Phase 1 through Phase 3

## Summary

Quant will evolve through three sequential product phases:

1. Establish an evidence-first decision workflow.
2. Add a deterministic natural-language Strategy Studio.
3. Add portfolio intelligence and thesis-lifecycle monitoring.

Each phase has an explicit exit gate. Work from a later phase should not bypass the
trust, validation, and audit foundations required by an earlier phase.

## Product Direction

Quant should remain an AI-assisted investment-research and paper-trading platform.
The AI layer may retrieve evidence, synthesize research, extract structured data, and
propose strategies. Deterministic application services must own calculations,
validation, portfolio constraints, authorization, and trading-state transitions.

The intended end-to-end workflow is:

```text
Research → Thesis → Strategy → Validation → Paper Allocation → Monitoring → Review
```

The product should differentiate through evidence provenance, reproducibility,
validation quality, portfolio context, and user-owned investment memory rather than
through opaque price predictions or access to a particular language model.

## Goals

1. Make every material recommendation traceable to current evidence.
2. Turn natural-language strategies into inspectable and reproducible rules.
3. Evaluate ideas in the context of the user's complete paper portfolio.
4. Measure whether prior forecasts, strategies, and decisions added value.
5. Preserve the existing paper-trading and decision-support boundary.

## Non-Goals

1. Live brokerage execution.
2. Autonomous or unconstrained LLM trading.
3. Intraday or low-latency trading infrastructure.
4. Derivatives strategy support.
5. Multi-user tenancy, billing, or enterprise access controls.
6. Claims of expected returns based on backtests or paper-trading results.

Live execution may be evaluated as a separate Phase 4 only after sustained
paper-trading validation, deterministic risk controls, operational readiness, and
jurisdiction-specific legal review.

## Guiding Principles

1. **Evidence before inference:** label reported facts, calculated facts, forecasts,
   and model interpretation separately.
2. **Freshness by default:** stale or expired evidence must be excluded automatically,
   not merely marked for manual cleanup.
3. **Deterministic decisions:** AI may propose; typed and testable services calculate,
   validate, and apply state changes.
4. **Human review:** parsed strategies and material portfolio actions require an
   inspectable preview and explicit confirmation.
5. **Reproducibility:** retain the evidence, model, prompt, strategy version,
   assumptions, and simulation configuration needed to reconstruct a decision.
6. **Portfolio context:** assess a proposed position against existing holdings and
   correlated risks rather than in isolation.
7. **Measured confidence:** do not present verbal model confidence as a calibrated
   probability.

## Phase 1 — Evidence-First Decision Loop

### Objective

Complete and harden the existing research-to-paper-trading workflow before expanding
the product surface.

### User Outcome

A user can move from sourced research to a reviewed thesis, validated simulation, and
paper-portfolio decision while seeing where the evidence came from and whether it is
still current.

### Scope

#### Research trust

1. Present Principles and Market Research as distinct workflows.
2. Surface source type, publication date, ingestion date, expiration, reliability
   tier, citations, and relevant source excerpts.
3. Exclude expired market-opinion evidence from every database, semantic-search, and
   agent retrieval path by default.
4. Show missing, stale, or contradictory evidence instead of silently filling gaps.
5. Retire the legacy ARK-specific service, index references, and user-facing labels
   after the shared market-opinion path is verified.

#### Workflow completion

1. Complete the Agent-to-Simulation handoff for parsed portfolio holdings.
2. Preserve the existing human-confirmation step before running a parsed strategy.
3. Link a simulation result to the research, thesis, strategy text, and assumptions
   that produced it.
4. Record paper-portfolio decisions and their supporting simulation.

#### Quality and audit foundation

1. Add focused automated coverage for:
   - strategy-parser normalization and fallback behavior;
   - stale-evidence exclusion and TTL handling;
   - knowledge ingestion and provenance fields;
   - portfolio cash, position, and transaction guards;
   - Agent-to-Simulation handoff contracts.
2. Add a versioned decision record containing:
   - source and thesis identifiers;
   - strategy input and normalized representation;
   - selected AI provider and model;
   - simulation parameters and result identifier;
   - user confirmation and paper action;
   - creation timestamps.
3. Make swallowed ingestion and extraction failures observable to the user or logs.

### Implementation Sequence

1. Establish tests around the existing parser, retrieval, and portfolio behavior.
2. Enforce freshness in all structured and semantic retrieval paths.
3. Complete the portfolio simulation handoff.
4. Add provenance presentation and the decision record.
5. Retire ARK-specific paths after migration verification.

### Acceptance Criteria

1. An expired market-opinion item is absent from all default user and agent searches.
2. Every displayed research result exposes its source and freshness metadata.
3. An Agent response containing portfolio holdings can prefill portfolio simulation,
   show parsing warnings, and require confirmation.
4. A paper transaction linked to an AI-assisted workflow can be reconstructed from
   its evidence, thesis, strategy, simulation, model, and confirmation records.
5. Parser, retrieval, handoff, and portfolio guard tests pass in an automated test run.
6. No active application path or label depends on the legacy ARK-specific service.

### Exit Gate

Every material AI-assisted paper-trading decision is traceable to current evidence,
passes tested application guards, and can be reproduced from stored inputs.

### Indicative Effort

Three to five focused development weeks. This is a planning range, not a delivery
commitment.

## Phase 2 — Natural-Language Strategy Studio

### Entry Criteria

1. Phase 1 acceptance criteria are satisfied.
2. The decision record and retrieval freshness policy are active.
3. Existing simulation behavior has automated regression coverage.

### Objective

Turn natural-language strategy ideas into typed, editable, deterministic, and
validation-gated strategy definitions.

### User Outcome

A user can describe a strategy, inspect and edit the normalized rules, understand
assumptions and warnings, compare versions, and evaluate credible out-of-sample
behavior before paper deployment.

### Scope

#### Strategy representation

1. Define a versioned strategy schema or DSL that explicitly represents:
   - universe and eligibility rules;
   - indicators and data dependencies;
   - feature-availability lag;
   - entry and exit conditions;
   - rebalance timing and order timing;
   - position sizing and allocation;
   - transaction-cost assumptions;
   - portfolio and instrument constraints.
2. Compile the normalized representation into deterministic simulation behavior.
3. Render the representation as an editable rule tree or structured form.
4. Show semantic differences between strategy versions.
5. Preserve the original prompt, parser output, user edits, and final definition.

#### Validation

1. Add static checks for unsupported data, same-bar signal/fill assumptions, invalid
   allocations, impossible rules, and likely look-ahead leakage.
2. Strengthen chronological walk-forward evaluation.
3. Keep model selection and preprocessing inside each training window where relevant.
4. Add an untouched final holdout period.
5. Model configurable commissions, spread, slippage, and signal-to-order delay.
6. Compare against relevant baselines such as cash, buy-and-hold, and simple
   allocation strategies.
7. Present turnover, sample length, drawdown, and regime coverage alongside returns.
8. Block or prominently warn on failed validation gates before paper deployment.

The following concrete simulator-realism upgrades (from a 2026 SOTA review of the
daily-close engine) are in scope for this phase and should be specified when the
Phase 2 implementation change spec is written:

1. Rolling / blocked walk-forward with purged, embargoed time-series
   cross-validation, replacing the current single 70/30 split.
2. Volatility-targeted position sizing and risk budgeting, replacing all-in sizing.
3. Liquidity-aware slippage as a function of order size versus ADV, rather than a
   fixed bps assumption alone. (A full Almgren-Chriss / square-root impact model
   remains out of scope while data is daily-close granularity.)
4. Regime-aware Monte Carlo using vol-clustered or state-conditioned resampling,
   replacing i.i.d. return resampling.
5. Dividend and corporate-action total-return handling in the price ingestion path.

#### Experiment management

1. Version strategy definitions and simulation configurations.
2. Track attempted strategy variants to make repeated tuning visible.
3. Allow side-by-side comparison using the same data snapshot and assumptions.
4. Produce a concise, human-readable strategy card for each version.

### Implementation Sequence

1. Specify the versioned strategy schema and conversion from the current parser.
2. Add deterministic compilation and schema validation.
3. Build the structured editor and semantic-diff experience.
4. Upgrade costs, chronological validation, holdout, and baseline comparisons.
5. Add experiment comparison and paper-deployment gates.

### Acceptance Criteria

1. The same normalized strategy and data snapshot produce reproducible results.
2. No strategy reaches simulation with an invalid schema.
3. Users can inspect and edit every executable rule before simulation.
4. Strategy changes produce a readable semantic diff and a new immutable version.
5. Results separate in-sample, walk-forward, and untouched holdout performance.
6. Reports include modeled costs, turnover, drawdown, sample size, and baselines.
7. Known leakage and unsupported execution assumptions trigger deterministic checks.
8. A strategy that fails mandatory validation cannot be silently promoted to paper use.

### Exit Gate

Natural-language strategies compile into deterministic, reviewable rules and produce
reproducible validation reports with credible out-of-sample evidence.

### Indicative Effort

Six to ten focused development weeks after Phase 1.

## Phase 3 — Portfolio Intelligence and Thesis Monitoring

### Entry Criteria

1. Phase 2 strategy definitions and validation reports are versioned.
2. Paper decisions are linked to positions and supporting theses.
3. Historical portfolio snapshots are available for deterministic analysis.

### Objective

Evaluate ideas and monitor decisions at the portfolio level, including the continued
validity of their supporting evidence.

### User Outcome

Before adding a position, the user can see its effect on portfolio risk. After making
a paper decision, the user can see whether supporting assumptions remain valid and
whether similar past decisions were well calibrated.

### Scope

#### Portfolio analysis

1. Add position, sector, and configurable category concentration.
2. Add return correlation and contribution-to-risk analysis.
3. Show the marginal effect of a proposed position on volatility, drawdown exposure,
   liquidity, and concentration.
4. Detect duplicated or highly correlated theses across holdings.
5. Add deterministic portfolio limits and warnings for paper allocation.

#### Thesis lifecycle

1. Store supporting assumptions and explicit invalidation conditions.
2. Monitor new filings, fundamentals, prices, and persisted research for material
   evidence changes.
3. Distinguish informational alerts from deterministic limit breaches.
4. Require source-backed explanations for changes in thesis status.
5. Preserve the history of thesis revisions and user responses.

#### Calibration and review

1. Record forecast horizon, expected direction or range, and stated uncertainty in a
   structured form.
2. Compare forecasts with realized outcomes after the defined horizon.
3. Provide decision postmortems using the evidence available at decision time.
4. Report performance by strategy, evidence source, model version, and market regime
   without implying causal attribution where it cannot be established.
5. Add downgrade-to-review or paper-allocation warnings when monitored quality falls
   below defined thresholds.

### Implementation Sequence

1. Establish historical portfolio snapshots and a deterministic risk model.
2. Add pre-allocation concentration, correlation, and marginal-risk analysis.
3. Add structured thesis assumptions and invalidation conditions.
4. Add evidence-change monitoring and review workflows.
5. Add forecast calibration and decision postmortems after sufficient observations
   exist.

### Acceptance Criteria

1. Every proposed paper allocation is evaluated against the complete portfolio.
2. Risk calculations use versioned inputs and can be reproduced.
3. Users can identify concentration and correlated-thesis warnings before allocation.
4. Each monitored thesis has explicit supporting assumptions and invalidation rules.
5. Evidence-change alerts cite the new evidence and the affected assumption.
6. Forecast outcomes are evaluated only after their declared horizon.
7. Postmortems reconstruct the information available at the original decision time.
8. Portfolio limits are enforced in application code rather than through AI prompts.

### Exit Gate

Quant evaluates decisions in portfolio context, monitors whether their supporting
evidence remains valid, and measures historical decision quality without relying on
unverifiable model confidence.

### Indicative Effort

Eight to fourteen focused development weeks after Phase 2. Calibration features may
require additional elapsed time to accumulate meaningful observations.

## Cross-Phase Technical Requirements

1. Use point-in-time semantics where source data supports them. Store publication,
   ingestion, effective, and revision timestamps separately.
2. Do not silently overwrite historical source values required to reproduce a
   simulation or decision.
3. Keep AI tools read-only unless a typed application service validates and applies a
   proposed state change.
4. Enforce authorization, freshness, validation, and risk rules in backend code.
5. Keep secrets and brokerage credentials out of prompts, retrieved content, and
   generated strategy code.
6. Record provider, model, prompt or workflow version, retrieved sources, tool calls,
   and structured outputs for material decisions.
7. Treat uploaded and retrieved content as untrusted input and test for prompt
   injection and malformed data.
8. Make provider-specific adapters replaceable; product behavior must not depend on
   one frontier model.

## Dependencies and Provider Direction

The roadmap does not require an immediate platform migration. The current stack can
support Phase 1, with targeted schema and test additions.

Potential later upgrades should be driven by measured requirements:

1. **Data:** retain FMP for current MVP coverage; evaluate Tiingo, Massive, Intrinio,
   or Databento when point-in-time fidelity, commercial rights, or higher-frequency
   data becomes necessary.
2. **Backtesting:** evaluate LEAN or NautilusTrader if the internal simulator cannot
   satisfy Phase 2 execution and reproducibility requirements.
3. **Portfolio analytics:** consider PyPortfolioOpt or Riskfolio-Lib after defining
   the required Phase 3 risk measures.
4. **AI observability:** extend the existing optional Langfuse integration or evaluate
   Phoenix when repeatable model and tool-call evaluations are introduced.
5. **Execution:** do not integrate Alpaca, Interactive Brokers, or another broker
   within Phases 1–3.

All data-provider evaluations must include commercial-use, display, redistribution,
correction, retention, and exchange-entitlement terms rather than comparing API price
alone.

## Delivery and Governance

1. Break each phase into focused implementation change specs before coding.
2. Keep this roadmap at `Proposed` until Phase 1 scope and sequencing are approved.
3. Mark a phase `In Progress` only when its first implementation change spec begins.
4. Record acceptance evidence before marking a phase complete.
5. Update `product_note.md` and `code_context.md` only when behavior is implemented,
   not when it is merely planned.
6. Reassess later-phase scope at each exit gate using product feedback and measured
   system behavior.

## Roadmap-Level Acceptance Criteria

1. Each phase has an approved implementation spec, owner, and acceptance evidence.
2. No later-phase feature bypasses an earlier phase's trust or validation gate.
3. Documentation distinguishes current capabilities from proposed roadmap work.
4. The product remains paper-only throughout Phases 1–3.
5. Claims about strategy quality are supported by reproducible validation and clearly
   labeled limitations.
