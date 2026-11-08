# App Simplification Change Spec

**Date:** 2026-11-07  
**Status:** Proposed - implementation not authorized by this review  
**Perspective:** Fintech principal architecture and product workflow review  
**Scope:** Navigation, progressive disclosure, research, strategy testing, and paper-portfolio handoffs

## 1. Executive Decision

Simplify Quant around three investment workspaces:

```text
Portfolio                 Research                  Strategies
Overview / Positions      Company / Library          Saved strategies
Activity                  Discover                   Draft / Review / Test

                   Contextual "Ask AI" panel
                   Secondary AI settings
```

Make Portfolio the default landing page. Treat AI as assistance within a task, not
another destination the user must visit. Make Strategy Studio the canonical strategy
workspace, but do not assume that its current runtime already satisfies all migration
and paper-use gates.

The objective is fewer decisions and less repeated input, not simply fewer pages.
Keep source freshness, risk warnings, deterministic checks, and confirmation visible
when they affect a decision.

**Planning assumption:** The primary user is an individual investor conducting
research and managing a paper portfolio, not a developer benchmarking LLMs or a
professional managing live execution. Confirm this assumption before implementation.

## 2. Review Evidence and Limits

Reviewed the current working tree, not only committed code or roadmap claims.
Inspected the live localhost UI without submitting research, simulations, or trades.
The worktree contains ongoing changes; this proposal does not overwrite them.

| Observation | Evidence | Product consequence |
|---|---|---|
| Nine equal-weight navigation links | [Layout](../frontend/src/components/Layout.tsx), [routes](../frontend/src/App.tsx) | Users must understand the application's modules before choosing a task. |
| Dashboard contains six financial cards, but positions and activity are separate pages | [Dashboard](../frontend/src/pages/Dashboard.tsx), [Holdings](../frontend/src/pages/Holdings.tsx), [Transactions](../frontend/src/pages/Transactions.tsx) | One portfolio job is fragmented across three destinations. |
| Research puts upload, Perplexity, and ChatGPT intake before the library | [Research](../frontend/src/pages/Research.tsx) | Consumption is subordinated to ingestion and integration setup. |
| Disabled Perplexity still occupies a full panel; extraction controls repeat | [Research](../frontend/src/pages/Research.tsx) | Unavailable infrastructure consumes attention and space. |
| Embedded ChatGPT requires special browser setup; a separate paste/import path exists | [ChatGPTResearchPane](../frontend/src/components/ChatGPTResearchPane.tsx) | Integration mechanics obscure the research job. |
| Copilot exposes mode, four provider choices, model selection, sessions, and a separate multi-agent workflow | [Agent](../frontend/src/pages/Agent.tsx) | Users configure orchestration before asking an investment question. |
| Simulation and Studio both accept strategies and produce backtests | [Simulation](../frontend/src/pages/Simulation.tsx), [StrategyStudio](../frontend/src/pages/StrategyStudio.tsx) | Two testing paths have different contracts and controls. |
| Copilot backtest action still targets legacy Simulation | [Agent](../frontend/src/pages/Agent.tsx) | The old path remains embedded in the main workflow. |
| Proposal allocation navigates to `/portfolio`, which is not currently registered | [Agent](../frontend/src/pages/Agent.tsx), [routes](../frontend/src/App.tsx) | A material handoff can land on an empty application shell. |
| Portfolio API accepts decision context, but frontend buy/sell helpers send only symbol and shares | [portfolio router](../backend/routers/portfolio.py), [client](../frontend/src/api/client.ts) | Audit capability exists but is not wired through these UI actions. |
| Reviewed status and validation are separate Studio operations | [StrategyStudio](../frontend/src/pages/StrategyStudio.tsx), [strategy router](../backend/routers/strategies.py) | "Reviewed" must not be presented as validated or suitable for paper allocation. |

Live initial Research render contained 10 form controls and 26 buttons in the main
content, including disabled controls. These are a point-in-time DOM baseline, not a
usability score or a count of controls visible above the fold.

This is a product and architecture review, not a security audit, investment
recommendation, or certification of simulation accuracy. No user testing, performance
benchmarking, or financial calculations were performed. Existing roadmap documents
may lag the current implementation; proposed capabilities below are not as-built claims.

## 3. Goals and Non-Goals

### Goals

1. Reduce primary navigation from nine destinations to three.
2. Let users research a company, test an idea, and review a paper decision without
   re-entering the same context.
3. Put portfolio state, saved evidence, and saved strategies ahead of creation forms.
4. Replace infrastructure-first controls with stable, capability-aware defaults.
5. Preserve historical records, deep links, explicit errors, and human confirmation.

### Non-goals

- New analytics, forecasting, autonomous trading, live brokerage execution, or billing.
- A replacement backtest engine as part of the navigation redesign.
- New microservices, a generic workflow engine, or a new mandatory "investment case" entity.
- Removing data or endpoints merely because their UI is demoted.
- A cosmetic restyle without workflow consolidation.

## 4. Target Information Architecture

| Current surface | Target home | Treatment |
|---|---|---|
| Dashboard | Portfolio / Overview | Merge; summarize total value, cash, and P&L. Put funding history and detailed breakdowns in details. |
| Holdings | Portfolio / Positions | Keep the position table; move paper trades and cash changes into deliberate action dialogs. |
| Transactions | Portfolio / Activity | Keep filtering and transaction history; attach available decision lineage. |
| Market | Research / Company | Reuse company lookup, quote/profile, and price chart. |
| Research | Research / Library | Library first; Add source opens a focused intake flow. Keep Principles and Market Research distinguishable. |
| Screener | Research / Discover | Retain the existing screener as a secondary discovery tool, not a primary navigation item. |
| AI Copilot | Contextual Ask AI + conversation history | Reuse persistent sessions and the same conversation UI; retain the old URL during migration. |
| Strategy Studio | Strategies | One saved-strategy list and a detail workflow. |
| Simulation | Temporary legacy compatibility view | Remove from primary navigation only after handoffs are covered; retire later behind explicit gates. |

Settings are a secondary utility, not a fourth investment workspace. Avoid a second
sidebar filled with the old nine links. Local tabs must represent parts of the selected
job, rather than reintroduce every former feature.

### Portfolio

- Default view: summary, positions preview, recent activity, and a contextual Ask AI action.
- Separate paper Buy/Sell from Deposit/Withdraw so funding and investment actions are
  not mixed in one persistent form.
- Show "Paper portfolio" persistently. Use "Review paper trade" before final submission.
- Show quantity, price/as-of status where available, estimated cost, and cash/position
  impact in the confirmation. Revalidate in the server; a preview is not a reserved price.
- Link recorded AI-assisted decisions to their evidence and test run. Label historical
  transactions with missing lineage rather than inventing it.
- Do not add thesis-monitoring alerts until the supporting lifecycle logic exists.

### Research

- Default to the library; use Company and Discover as local views.
- Replace the three permanent intake panels with one Add source flow:
  upload file, paste text, or import an external research answer.
- Show the source-specific fields only after selecting the intake method.
- Preserve document classification, publication date, provenance, citations, and
  expiry policy. A compact list may move details into a source view, not discard them.
- Keep expired/unavailable evidence identifiable. Exclusion from recommendation
  retrieval is a backend policy; hiding a badge or adding a cleanup button is not a substitute.
- Replace the always-loaded ChatGPT iframe with explicit open-in-tab/copy-prompt and
  paste/import actions. Do not require weakening browser embedding protections.
- Put unavailable providers in settings with an explanation, not a disabled full-page panel.
- Retain provider/source provenance even when provider brands are removed from navigation.
- A company-to-strategy action should carry selected evidence identifiers and ticker
  into a draft, never automatically infer that the company merits purchase.

### Strategies

Start with saved strategies and one New strategy action. Within a strategy:

```text
Draft -> Review rules -> Test -> Review results
                              -> Review paper allocation, only if eligible
```

- Draft: description, name, and minimal test period/benchmark inputs.
- Review: readable holdings, rules, assumptions, and blocking findings.
- Test: run the deterministic test; present validation separately from compilation
  and human review, even if the UI coordinates these steps.
- Results: benchmark-relative performance, drawdown, and validation outcome first;
  trade log, fold tables, bootstrap paths, and additional risk metrics in details.
- Keep assumptions and material warnings in the summary; "advanced" must not hide
  information required to interpret results.
- Put version history alongside the strategy, not as a numbered step between
  validation and results. Reviewed versions remain immutable.
- Raw JSON/parser output is an advanced inspection tool, not the default editing experience.
- Do not force all legacy strategy descriptions through an adapter that silently
  changes holdings, rules, normalization, timing, costs, or unsupported capabilities.

### Contextual AI

- Open the same assistant panel with the current symbol, selected sources, strategy
  version, or portfolio context visibly attached and removable.
- Preserve session history; collapse the session list until requested.
- Default to a verified available configuration, not blindly to the first model
  returned. Report unavailable configuration explicitly.
- Keep provider/model selection in shared settings and an optional per-session override.
  Existing session choices remain authoritative unless the user changes them.
- Record the actual provider/model used for each material result, including any
  explicitly accepted fallback. Do not silently switch cloud/local privacy boundaries.
- Offer "Analyze company" as a task. Put analysts/debate/trader phases in run details.
- Reuse the multi-agent proposal result rather than introduce another analysis dashboard.
- Show AI opinion, deterministic risk checks, validation status, and user approval as
  different concepts. Neither confidence dots nor "Risk Approved" establishes suitability.
- AI can prepare a draft or trade preview, never bypass review or execute automatically.

## 5. Architecture: Recompose, Do Not Replatform

Keep React/React Router and the FastAPI modular application. Consolidate user-facing
workspaces without merging unrelated domain services or rewriting persistence.

### Small shared frontend contracts

Extract existing behavior into shared components only where the new layout needs reuse:

1. One provider/settings implementation for Agent, extraction, and strategy parsing.
2. One persistent conversation component, usable in the contextual panel and legacy
   conversation route, not separate chat implementations.
3. One paper-action review flow, reachable from positions and AI proposals.
4. One typed handoff contract carrying relevant symbol, session, document/thesis,
   strategy/version, and simulation identifiers.

Use existing domain identifiers, not a parallel case database. Persist supported
draft inputs when needed; transient router state alone must not be the only copy.
Resolve persisted objects by ID for refreshable links. Do not put complete private
research or chat messages into URLs.

### Backend boundaries and tightly coupled work

- Market/screener services retrieve and calculate; AI synthesizes and proposes.
- Strategy services parse, compile, execute, and validate deterministic definitions.
- Portfolio services enforce cash/position guards and own state changes.
- Decision records retain source, strategy, test, model, and confirmation context.
- Wire the existing optional decision-context payload for AI-assisted trades.
  Manual paper trades stay possible and are identified as manual.
- Close the tightly coupled partial-success risk: the current buy path commits the
  transaction before recording decision context. Make portfolio change and required
  decision lineage atomic for assisted actions, or implement an explicit recoverable
  failure contract before presenting a successful reviewed trade.
- Enforce any new paper-use eligibility rules on the server, not just a disabled button.
  Do not equate a compile-success flag with an accepted validation report.

This last group changes behavior and requires focused backend regression coverage;
it is not a prerequisite for merely moving navigation links.

## 6. Migration and Compatibility

Follow the existing [backtest improvement spec](backtest_strategy_improvement_change_spec.md)
for canonical runtime and legacy deprecation. This proposal coordinates presentation
and handoffs; it does not replace that spec's correctness gates.

| Existing URL | Compatibility policy |
|---|---|
| `/` | Portfolio overview after shell consolidation. |
| `/holdings`, `/transactions` | Aliases to the corresponding portfolio view; preserve relevant filters. |
| `/portfolio` | Register a real destination and support the proposal prefill contract with review, not submission. |
| `/market`, `/research`, `/screener` | Aliases or existing routes rendered within the Research workspace. |
| `/agent` | Retain the session-capable compatibility view while contextual AI is introduced. |
| `/strategy-studio` | Alias to Strategies without losing draft/version selection. |
| `/simulation` | Retain labeled legacy view and its query/state handoffs until semantic migration is verified. |

Before removing legacy Simulation:

1. Inventory frontend, MCP, scripts, and backend parser callers.
2. Test representative single-instrument and portfolio transfers, including unsupported
   rules, parser warnings, weight normalization, dates, benchmark, costs, and timing.
3. Route new Copilot strategy actions to a reviewed Studio draft; parser failure is
   visible and must not silently become a single-ticker fallback.
4. Mark historical results with runtime/version assumptions. Never relabel or recompute
   legacy results as canonical results without an explicit new run.
5. Confirm saved results can be reopened and compatibility users have a supported path.
6. Remove the navigation entry first; remove the route and APIs only after all active
   callers are migrated and explicit sign-off is obtained.

Release reversible shell changes separately from backend eligibility changes.
Keep route aliases and existing data; no destructive schema cleanup in this project.

## 7. Delivery Sequence

| Stage | Scope | Depends on | Exit gate |
|---|---|---|---|
| A - Lock scope and baseline | Confirm primary user; inventory callers and handoffs; capture representative populated/empty UI states | None | Agreed three-workspace IA and regression scenarios; no new feature expansion during simplification |
| B - Navigation and read-first views | Three primary links; merge portfolio views; library-first research; secondary Discover; collapse intake; register portfolio handoff | A | Existing actions/data remain reachable, old URLs work, and no permanent disabled integration panels remain |
| C - Shared AI and complete handoffs | Shared settings and conversations; contextual panel; source/strategy lineage; paper review and atomic assisted decision recording | B | No duplicate chat/provider implementations; contexts survive navigation; cancellation makes no paper change |
| D - Canonical strategy experience | Saved-first Studio, Review/Test/Results flow, advanced details, Copilot-to-Studio transfer | A; canonical runtime/data/validation gates from backtest spec for full migration | Supported strategies preserve semantics; unsupported ones fail explicitly; old runs remain distinguishable |
| E - Retire legacy entry points | Remove Simulation from primary workflows and later consider route/API retirement | C, D; caller inventory and migration sign-off | No active dependency removed; compatibility and rollback verified |

B is the recommended first implementation slice: it addresses visible crowding
without bundling engine changes. C and D can be staged independently after their
contracts are agreed; E requires both.

Indicative planning range: B could take 3-5 focused development days; C and the UI
portion of D each roughly 1-2 focused weeks. These are not commitments and exclude
unfinished canonical backtest correctness work. Re-estimate after A and after
reconciling the current dirty worktree.

## 8. Acceptance Criteria and Verification

### Product checks

- Exactly three primary investment navigation destinations at desktop and mobile widths.
- Every workspace starts with useful saved/current content or a focused empty state,
  not a wall of configuration.
- No provider/model chooser is visible in the default workspace body; settings and
  session overrides remain accessible.
- No disabled Perplexity panel or automatically loaded external ChatGPT iframe in
  the default Research view.
- Initial Research main-content controls target at most 8 buttons and 3 form controls
  on the same empty-library baseline used in this review, excluding open dialogs
  and the closed assistant. Verify DOM counts, not a screenshot estimate.
- At 375px, 768px, and 1440px, navigation and primary actions remain usable without
  page-level horizontal scrolling; dense tables may scroll within their own container.
- All expanded details/dialogs are keyboard accessible, have explicit labels,
  restore focus, and expose failures rather than empty success-shaped views.

### Workflow and fintech regression checks

1. Company -> selected evidence -> strategy draft -> reviewed rules -> test result
   does not require re-entering the ticker or selected sources.
2. Parse/transfer failure remains an explicit failure; no implicit buy-and-hold or
   single-ticker substitution.
3. Old routes, query parameters, proposal prefills, and session history survive
   shell migration and browser back/forward navigation.
4. Saved drafts/results reopen after refresh; displayed context matches persisted IDs.
5. Blocked rules or ineligible validation cannot be bypassed through a direct API
   call when paper eligibility is claimed.
6. Canceling a trade preview has no side effect. Submission rechecks cash/positions.
7. Each assisted paper trade links to actual evidence/run/model context and user
   confirmation; required audit-write failure cannot leave an unreported partial success.
8. Manual paper trades continue working; missing historical lineage is clearly labeled.
9. Expired/missing research, unavailable models, and failed portfolio loads stay explicit.
10. Canonical/legacy results retain their original assumptions and identifiers.

Use the existing TypeScript build and ESLint commands for changed frontend code.
Add focused contract/UI and backend fixture tests using the repository's actual
test setup discovered at implementation time; do not install a new framework merely
for this planning document. Avoid live market/provider calls in regression fixtures.

Proposed usability pilot: at least five representative users complete company research,
strategy testing, and a paper trade without coaching. Target at least 80% completion
per task and a 25% median time reduction against the measured current UI. These are
future acceptance targets, not results established by this review.

## 9. Roadmap Alignment and Decision Gate

This is a cross-cutting simplification track, not a fourth feature phase.
It preserves the [product roadmap](product_development_roadmap_change_spec.md)'s
evidence-first direction and the backtest track's controlled deprecation.
Navigation consolidation does not waive freshness, reproducibility, or validation gates.

Before implementation, approve:

1. The individual-investor/paper-portfolio primary-user assumption.
2. Three workspaces with Portfolio as home and AI as contextual assistance.
3. Open-in-tab/import instead of the default embedded ChatGPT pane.
4. Strategy Studio as the canonical destination, with gated legacy compatibility.

**Principal-architect recommendation:** Ship the read-first shell first, then remove
duplicated configuration and repair context-preserving handoffs. Stop expanding
top-level features until those workflows are coherent. Preserve sophistication in
the domain services and evidence; remove it from the user's navigation burden.
