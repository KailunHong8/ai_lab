# Change Specs

This folder contains the product note, dated product/engineering change specifications,
and their historical archive.

## Rules

1. Store all new change specs in this folder.
2. Use file names in the pattern: `<topic>_change_spec.md`.
3. Keep each spec self-contained with date, status, goals, non-goals, implementation plan, and acceptance criteria.
4. Keep historical specs unless explicitly deprecated and moved to `archive/`.

## Current Documents

1. [`product_note.md`](product_note.md) — current product positioning, decisions, and gaps.
2. [`product_development_roadmap_change_spec.md`](product_development_roadmap_change_spec.md) — proposed three-phase product roadmap and exit gates.
3. [`phase1_evidence_loop_change_spec.md`](phase1_evidence_loop_change_spec.md) — Phase 1 implementation spec (freshness, handoff, decision ledger, tests).
4. [`phase2_strategy_studio_change_spec.md`](phase2_strategy_studio_change_spec.md) — Phase 2 implementation spec (typed strategies, validation, realistic daily-bar simulation, and user manual).
5. [`research_workflow_change_spec.md`](research_workflow_change_spec.md) — research workflow design and acceptance criteria.
6. [`simulation_strategy_parser_change_spec.md`](simulation_strategy_parser_change_spec.md) — strategy parsing design and acceptance criteria.
7. [`backtest_strategy_improvement_change_spec.md`](backtest_strategy_improvement_change_spec.md) — standalone backtest improvement and legacy simulation deprecation track (outside Phase 2).
8. [`../code_context.md`](../code_context.md) — canonical as-built engineering reference.

## Archive

[`archive/v1_initial_functional_spec.md`](archive/v1_initial_functional_spec.md) is the
deprecated original MVP functional specification. It is historical only and must not be
used as the source of current implementation details.
