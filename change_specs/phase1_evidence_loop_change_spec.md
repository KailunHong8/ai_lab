# Phase 1 Implementation Spec — Evidence-First Decision Loop

**Date:** 2026-07-11
**Status:** Proposed
**Parent:** [`product_development_roadmap_change_spec.md`](product_development_roadmap_change_spec.md) — Phase 1

## Summary

Implement the Phase 1 exit gate from the roadmap: every material AI-assisted paper-trading
decision must be traceable to current evidence, pass tested application guards, and be
reproducible from stored inputs.

This spec pins the schema, freshness mechanism, handoff contract, and test harness so the
work can be implemented without further design decisions.

## Goals

1. Exclude expired market-opinion evidence from every default retrieval path.
2. Surface provenance and freshness on research results the user and agent see.
3. Complete the Agent → portfolio-simulation handoff with a human-confirm gate.
4. Persist simulation runs as first-class, reproducible records.
5. Record an auditable decision trail for AI-assisted paper trades, linked to the run.
6. Establish a test harness and cover the highest-risk contracts.
7. Retire the orphaned ARK-specific service and align naming.

## Non-Goals

1. Point-in-time fundamentals or intraday data (Phase 2+).
2. A typed strategy DSL / rule editor (Phase 2).
3. Portfolio-level risk analytics (Phase 3).
4. Any live brokerage integration.
5. Alembic/migration framework adoption — new tables auto-create under `create_all`;
   this spec adds no new columns to existing tables.

## Current State (verified 2026-07-11)

- `Document` and `Thesis` already carry `expiration_at`, `reliability_tier`,
  `recency_flag`, `source_type`, `fund` (`backend/models.py:97-133`).
- `search_theses` already supports `exclude_stale` (`backend/services/knowledge_base.py:27,41-44`)
  but the agent dispatch calls it without that argument (`backend/services/bedrock.py:254`).
- `search_market_opinion` has **no** freshness filter (`backend/services/market_opinion_research.py:145-196`).
- Chroma metadata is written at `add_document` (`market_opinion_research.py:58-94`),
  `_index_document` / `_async_index_document` (`backend/routers/knowledge.py:36-68`), and
  `rebuild_market_opinion_index` (`market_opinion_research.py:201-244`). None write an
  expiration field into metadata.
- Bedrock and Ollama share `_dispatch_tool` (`ollama_client.py:18,163`), so one fix covers both.
- `cleanup_stale` exists but is manual and unscheduled (`knowledge.py:525-544`).
- Agent handoff passes only `strategy`, `symbol`, dates, capital (`frontend/src/pages/Agent.tsx:281-291`);
  Simulation defaults to single mode with a static `DEFAULT_PORTFOLIO` (`frontend/src/pages/Simulation.tsx:159-172`).
- `_parse_strategy_dual` already returns `holdings`, `trading_rules`, `parse_warnings`,
  `strategy_mode` (`simulation.py:84-156`).
- `/api/simulation/run` and `/run-portfolio` compute a result payload on request and
  persist nothing (`simulation.py:763-839, 844+`). Response payloads include scalar
  metrics + trade stats plus `equity_curve`, `trades`, `parsed_rules`, `benchmark`,
  cost fields, and optional `monte_carlo`/`walk_forward`/`stress_tests` blocks.
- `backend/services/ark_research.py` is orphaned (no importers); `chroma_ark/` exists on disk.
- No test harness exists (`backend/requirements.txt` is the only config; no pytest/vitest).

## Work Item 1 — Freshness Enforcement

### 1a. Structured thesis retrieval (DB)

- Change the service default so freshness is on unless explicitly disabled:
  `search_theses(..., exclude_stale: bool = True)` in `knowledge_base.py`.
- Update the agent dispatch to rely on that default (or pass `exclude_stale=True`
  explicitly) at `bedrock.py:254`.
- The `/api/knowledge/theses` endpoint keeps an explicit `exclude_stale` query param
  (default `True`) so an admin view can pass `False` to inspect expired items.

### 1b. Market-opinion retrieval (Chroma)

Chroma metadata values are strings/scalars and cannot express "null OR future" cleanly,
so store a numeric sentinel and filter with a single comparison.

- At every index path, add `expiration_epoch` to metadata:
  - web research with a TTL → `int(expiration_at.timestamp())`
  - evergreen / no expiry → sentinel `9999999999` (year 2286).
  - Paths to update: `add_document` (`market_opinion_research.py`), `_index_document`
    and `_async_index_document` (`knowledge.py`), and `rebuild_market_opinion_index`.
- Add `exclude_stale: bool = True` to `search_market_opinion`. When true, add
  `where={"expiration_epoch": {"$gt": int(now_utc.timestamp())}}` merged with any
  existing `fund` / `source_type` filters (using the existing `$and` composition).
- The keyword fallback (`_keyword_search`) must apply the same epoch check locally.
- Agent dispatch (`bedrock.py:283`) relies on the `True` default.

### 1c. Automatic cleanup

- Call the existing stale-removal logic on startup via the FastAPI lifespan in
  `backend/main.py` (best-effort, wrapped so a failure never blocks startup).
- Refactor the body of `cleanup_stale` into a reusable
  `remove_expired_market_opinion(db) -> int` so both the route and startup call it.
- Add a "Clean expired research" action in `Research.tsx` that calls
  `DELETE /api/knowledge/cleanup-stale` and shows the removed count.

### Acceptance — Work Item 1

- A `Thesis`/`Document` with `expiration_at` in the past is absent from
  `search_theses` and `search_market_opinion` defaults, and from the agent tools.
- Passing `exclude_stale=False` still returns expired items (admin path).
- Startup removes already-expired market-opinion docs without raising.

## Work Item 2 — Provenance Presentation

- `/api/knowledge/theses` and `/api/knowledge/search-market-opinion` already return
  `source_type`, `fund`, `reliability_tier`, `recency_flag` (theses) and `metadata`
  (market opinion). Extend the market-opinion result to also surface
  `expiration_epoch`/`expiration_at` and any stored citation reference.
- In `Research.tsx`, show for each item: source type, fund/source label, published or
  ingested date, reliability tier, and an "expired/expires" indicator. Citations
  (`citations_json`) shown where present.
- No backend schema change; this is serialization + UI.

### Acceptance — Work Item 2

- Every research row in the UI shows source type, a date, reliability, and freshness.
- Expired items (when shown via the admin toggle) are visually marked expired.

## Work Item 3 — Agent → Portfolio Simulation Handoff

### Contract

- In `Agent.tsx`, the "Run Backtest" action first calls `parseStrategy` (existing
  `POST /api/simulation/parse-strategy`).
  - If `holdings.length > 0`: navigate to `/simulation` with router state
    `{ strategy, holdings, tradingRules, parseWarnings, mode: "portfolio" }`.
  - Else: preserve current single-ticker behavior.
- Use react-router `navigate("/simulation", { state })` rather than query params to
  avoid URL-length limits on large allocation tables. Keep the existing query-param
  path as a fallback for single mode.
- In `Simulation.tsx`:
  - Read `location.state`; when `mode === "portfolio"` and holdings exist, set
    `mode="portfolio"`, populate the holdings table from parsed holdings (map
    `allocation_pct` → `weight`), and show `parseWarnings`.
  - Require the existing human-confirm step (`confirmedParsed`) before a run is allowed;
    do not auto-run.

### Acceptance — Work Item 3

- An agent reply containing an allocation table pre-fills portfolio-mode holdings,
  shows parse warnings, and blocks the run until the user confirms.
- A rules-only / single-ticker reply still uses the single-ticker path.

## Work Item 4 — Persisted Simulation Runs

Make every simulation a first-class stored record so a decision can point to the exact
run behind it and Phase 3 postmortems can re-open historical runs.

### Schema (new table — no migration needed)

Add to `backend/models.py`:

```
class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: str (uuid, pk)
    created_at: datetime = utcnow
    mode: str                          # "single" | "portfolio"
    strategy_description: str | None
    symbol: str | None                 # single mode
    holdings_json: str | None          # portfolio mode: normalized [{ticker, weight}]
    parsed_strategy_json: str | None   # _parse_strategy_dual snapshot (rules + warnings)
    start_date: str
    end_date: str
    initial_capital: Numeric
    benchmark_symbol: str
    commission_bps: float
    slippage_bps: float
    provider: str | None
    model: str | None
    request_json: str                  # full request needed to reproduce the run
    summary_json: str                  # scalar metrics + trade stats + cost totals
    result_json: str | None            # full payload incl. equity_curve/trades/analytics
```

Design decisions:
- `request_json` captures everything required to re-run; `summary_json` holds the scalar
  analytics (Sharpe, Sortino, drawdown, alpha/beta, final value, total costs, trade
  stats) for cheap listing; `result_json` stores the full payload (equity curve, trades,
  Monte Carlo / walk-forward / stress blocks) for exact re-open. `result_json` is stored
  as-is from the endpoint payload — no separate curve table in Phase 1.
- Runs are immutable once written; re-running produces a new row.

### Write path

- Persist a `SimulationRun` at the end of both `/api/simulation/run` (mode `single`) and
  `/api/simulation/run-portfolio` (mode `portfolio`), after the payload is built, and
  include `simulation_run_id` in the returned payload.
- Persistence must not break the response: wrap the write so a DB failure logs and still
  returns the computed payload. Both endpoints currently take no `db` session, so add the
  `get_db` dependency to persist.
- Add `GET /api/simulation/runs?limit=` (list, summary fields only) and
  `GET /api/simulation/runs/{id}` (full `result_json`) for audit and re-open.

### Acceptance — Work Item 4

- A successful `/run` and `/run-portfolio` each create a `SimulationRun` row and return
  its `simulation_run_id`.
- `GET /api/simulation/runs/{id}` returns a payload sufficient to reproduce and re-open
  the run; the list endpoint returns summary metrics without the full curve.
- A DB write failure does not prevent the simulation response from returning.

## Work Item 5 — Decision Ledger

### Schema (new table — no migration needed)

Add to `backend/models.py`:

```
class Decision(Base):
    __tablename__ = "decisions"
    id: str (uuid, pk)
    created_at: datetime = utcnow
    user_id: int                      # DEFAULT_USER_ID for now
    action: str                       # "BUY" | "SELL"
    symbol: str
    shares: Decimal | None
    price: Decimal | None
    transaction_id: int | None        # FK -> transactions.id
    provider: str | None              # bedrock | ollama | ollama-cloud
    model: str | None
    session_id: str | None            # FK -> chat_sessions.id (nullable)
    thesis_ids_json: str | None       # JSON list of Thesis.id used
    document_ids_json: str | None     # JSON list of Document.id cited
    strategy_text: str | None         # raw strategy description, if any
    strategy_parsed_json: str | None  # normalized holdings + rules snapshot
    simulation_run_id: str | None     # FK -> simulation_runs.id (Work Item 4)
    confirmed_by_user: bool = False
```

The decision links to a persisted `SimulationRun` (Work Item 4) rather than embedding the
simulation request/summary inline, so the full run is reproducible from the ledger.

### Write path

- Add `record_decision(...)` in a small `backend/services/decisions.py`.
- Extend the portfolio buy/sell endpoints to accept an optional `decision_context`
  (provider, model, session_id, thesis_ids, document_ids, strategy snapshot,
  `simulation_run_id`). When present, write a `Decision` row linked to the created
  `Transaction`. Absent context → no ledger row (manual trades stay lightweight).
- Add `GET /api/decisions?limit=` to list recent decisions for audit; joining
  `simulation_run_id` lets a caller fetch the full run via Work Item 4's endpoint.

### Acceptance — Work Item 5

- A buy/sell submitted with decision context produces a `Decision` row whose
  `transaction_id`, evidence ids, model, and `simulation_run_id` reconstruct the decision.
- Following `simulation_run_id` returns the run that informed the trade.
- `GET /api/decisions` returns the row.

## Work Item 6 — Retire Legacy ARK Path

- Delete `backend/services/ark_research.py` (confirmed no importers).
- Remove the `chroma_ark/` directory and any `ARK_DOCS_DIR` / `REBUILD_ARK_INDEX`
  references in `code_context.md`.
- Update ARK-specific wording to fund-neutral language:
  `screener.py:251` (`enrich` description) and `screener.py:6` docstring, and any
  "ARK theses" label in `Screener.tsx`.
- ARK remains a valid `fund` value in the shared collection; only the dedicated code path is removed.

### Acceptance — Work Item 6

- No module imports `ark_research`; app starts and screener enrichment still returns theses.
- No user-facing string implies ARK is the only fund.

## Work Item 7 — Observability of Silent Failures

- The mbox background extraction/index task swallows all exceptions
  (`knowledge.py:156-165`) and the agent research ingestion swallows errors. Replace
  bare `except Exception: pass` with structured logging (reuse the existing
  `llm_logger`/structlog) so failures are visible. Behavior otherwise unchanged.

## Test Harness

### Setup

- Add dev dependencies: `pytest`, `pytest-asyncio`, `httpx` (already used), `anyio`.
- Add `backend/tests/` with `conftest.py` providing:
  - an in-memory async SQLite engine (`sqlite+aiosqlite:///:memory:`) with
    `Base.metadata.create_all`, overriding `get_db`;
  - a FastAPI `AsyncClient` via `httpx.ASGITransport(app=app)`;
  - factory helpers to insert `Document`/`Thesis` rows with chosen `expiration_at`.
- Chroma and LLM calls are mocked/monkeypatched — tests must not hit network,
  Bedrock, Ollama, Perplexity, or FMP.

### What is actually testable (and worth it)

Grouped by cost/value.

**A. Pure functions — deterministic, no I/O (highest ROI):**
- `_parse_strategy_dual` normalization by feeding a fabricated LLM dict (monkeypatch
  `_llm_extract`): duplicate-ticker merge, invalid/non-positive allocation skipped +
  warning, ticker uppercasing incl. `BRK.B`, allocation renormalized to 100%,
  `strategy_mode` selection (`allocation_only` / `rules_only` / `allocation_and_rules`),
  `DEFAULT_ALLOCATION_RUN_RULES` fallback.
- The transaction-cost model (bps slippage + commission) given fixed inputs.
- The `expiration_epoch` sentinel/derivation helper (TTL → epoch, evergreen → sentinel).

**B. DB-backed service logic — in-memory SQLite (high ROI):**
- `search_theses` freshness: expired excluded by default; included when
  `exclude_stale=False`; `entity`/`fund`/`source_type`/`recency_flag` filters; ordering/limit.
- `remove_expired_market_opinion` deletes only past-dated market-opinion docs and
  returns the count; evergreen/future untouched.
- Portfolio guards: buy beyond cash rejected; sell beyond shares rejected; deposit/
  withdraw update `cash_balance`; average-cost math on buys.
- `SimulationRun` persistence: a fabricated payload is stored and reloaded intact; the
  list endpoint returns summary fields only; `GET /runs/{id}` returns the full result.
- `record_decision` persists, links to the transaction, and references a
  `simulation_run_id`; `GET /api/decisions` returns it.

**C. API contract — ASGI client (medium ROI):**
- `/api/knowledge/theses?exclude_stale=` default vs explicit behavior.
- `/api/simulation/parse-strategy` returns the four-field shape (with `_llm_extract` mocked).
- `/api/simulation/run` persists a `SimulationRun` and returns `simulation_run_id`
  (with `_parse_strategy`, `fmp_service`, and backtest internals mocked/stubbed).
- `/api/knowledge/cleanup-stale` removes expired and reports the count.

**D. Freshness in Chroma retrieval — with a fake collection:**
- Monkeypatch the Chroma collection with an in-memory fake so `search_market_opinion`
  can be asserted to add the `expiration_epoch > now` filter and to drop expired docs in
  the keyword fallback. (Validates our filter construction without a real vector store.)

**Frontend (optional, lower priority):**
- Add Vitest + React Testing Library; unit-test the Agent→Simulation mapping
  (`allocation_pct` → `weight`, `mode="portfolio"`, confirm-gate blocks run). Deferred if
  time-constrained; backend coverage is the priority.

### Not worth unit-testing in Phase 1

- Real LLM extraction quality (non-deterministic — belongs in a Phase 2 eval set, not unit tests).
- Real Chroma similarity ranking or embedding quality.
- Live FMP/Yahoo/Perplexity responses.
- Full backtest numeric outputs end-to-end (cover the cost model unit instead).

## Implementation Order

1. Test harness scaffold + Work Item 1a/1b freshness (with tests) → verify: group A/B pass.
2. Work Item 1c cleanup + startup hook → verify: cleanup test passes.
3. Work Item 4 persisted simulation runs → verify: run persistence + run endpoints tests pass.
4. Work Item 5 decision ledger (links `simulation_run_id`) → verify: ledger + API tests pass.
5. Work Item 3 handoff → verify: frontend mapping (manual + optional Vitest).
6. Work Item 2 provenance UI → verify: manual UI check.
7. Work Item 6 ARK retirement → verify: app starts, screener test passes.
8. Work Item 7 logging → verify: no bare pass remains in the two paths.

## Acceptance Criteria (Phase 1 gate)

1. Expired market-opinion evidence is absent from all default user and agent searches;
   an explicit admin flag can still surface it.
2. Every displayed research result exposes source and freshness metadata.
3. An agent response with portfolio holdings pre-fills portfolio simulation, shows
   parse warnings, and requires confirmation before running.
4. Each simulation run is persisted as a `SimulationRun` and can be re-opened by id.
5. A paper transaction from an AI-assisted flow is reconstructable from its `Decision`
   row (evidence ids, model, strategy snapshot, linked `simulation_run_id`, confirmation).
6. Group A, B, and C tests pass in an automated `pytest` run.
7. No active code path or user-facing label depends on the legacy ARK-specific service.

## Documentation Updates (on completion, not before)

- `product_note.md`: move the relevant items out of "Remaining Product Gaps".
- `code_context.md`: remove ARK references; add `simulation_runs` and `decisions` tables,
  the new `/api/simulation/runs` and `/api/decisions` endpoints, freshness behavior,
  startup cleanup, and the `backend/tests/` harness.
