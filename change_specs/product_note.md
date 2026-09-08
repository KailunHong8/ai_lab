# Product Note — Quant Agentic Trading System

Last verified: 2026-07-11

Quant is an AI-powered paper-trading and investment-research platform. It provides
decision support only: it does not place real trades or connect to a brokerage.

## Product Positioning

Quant combines:

1. Paper-trading portfolio operations and mark-to-market reporting.
2. Market and fundamental data retrieval.
3. AI-assisted research synthesis.
4. Strategy simulation and risk analytics.
5. A user-curated knowledge base of source documents and extracted theses.

## Current Product Capabilities

### Market and portfolio

1. FMP-backed quote, profile, symbol search, and end-of-day price history, with
   Yahoo Finance fallback where FMP free-tier coverage is unavailable.
2. Paper-trading deposit, withdrawal, buy, and sell workflows with server-side
   cash and position guards.
3. Holdings, transaction history, and live mark-to-market portfolio summaries.

### AI copilot

1. Advice, research, and automatic intent-routing modes.
2. Bedrock, local Ollama, and Ollama Cloud provider/model controls.
3. Tool-assisted access to quotes, portfolios, screener history, structured theses,
   entity relationships, investing principles, and market-opinion research.
4. Persistent chat sessions.

### Research library

1. Manual text, file, and mbox ingestion with SHA256 deduplication.
2. Provider-selectable extraction of structured theses and entity relationships.
3. A two-lane taxonomy:
   - **Principles:** manually curated, evergreen investing frameworks.
   - **Market opinion:** fund letters and time-sensitive Perplexity research.
4. Perplexity research can be manually persisted with citation and 30-day TTL metadata.
5. Separate principles and shared market-opinion vector collections; the latter uses
   metadata filters for fund and source type.

### Screener and simulation

1. A six-criterion value screener with persisted run history and thesis enrichment.
2. Single-ticker and portfolio backtests with rule parsing, equity curves, and
   risk analytics including Sharpe, Sortino, Calmar, drawdown, alpha/beta,
   Monte Carlo, walk-forward, and stress-window analysis.
3. A strategy parser that can extract holdings, trading rules, parse warnings, and
   a buy-and-hold fallback from a strategy description.

## Product Decisions

### Knowledge workflow

The product uses a hybrid research workflow:

1. Principles and fund letters are manually curated to preserve source quality.
2. Perplexity provides optional, manually triggered market context.
3. Agent reasoning should use principles first, fund opinions second, and web context
   last; it should label sources and distinguish facts from forecasts.
4. Web research is time-sensitive and must not be the sole basis for a recommendation.

The detailed design and remaining work are tracked in
[`research_workflow_change_spec.md`](research_workflow_change_spec.md).

### Simulation workflow

Strategy descriptions can be parsed into holdings and rules so users can review the
result before simulating. The detailed design and remaining work are tracked in
[`simulation_strategy_parser_change_spec.md`](simulation_strategy_parser_change_spec.md).

### Product development roadmap

Proposed product development is organized into three gated phases: an evidence-first
decision loop, a natural-language Strategy Studio, and portfolio intelligence with
thesis monitoring. Scope, sequencing, and phase acceptance criteria are tracked in
[`product_development_roadmap_change_spec.md`](product_development_roadmap_change_spec.md).

## Remaining Product Gaps

1. Research UI does not yet present separate Principles and Market Research workflows
   or surface all provenance and recency metadata.
2. Expired market-opinion entries require explicit cleanup and are not automatically
   excluded from every retrieval path.
3. The legacy ARK-specific index/service remains to be fully retired.
4. The agent handoff does not yet prefill portfolio simulation from parsed holdings.
5. Parser and knowledge-workflow acceptance criteria lack automated test coverage.

## Constraints and Risks

1. FMP free-tier limits and coverage gaps remain; only end-of-day historical data is
   available for simulation.
2. Some fundamentals may be sparse or delayed when Yahoo is used as the fallback.
3. Extraction quality depends on the selected provider/model, and long documents may
   be truncated.
4. The simulator is a daily-close, fixed-bps engine positioned for strategy
   prototyping and educational risk analytics, not institutional execution realism.
   It uses simplified transaction-cost and slippage assumptions, a close-only fill
   model, and does not model liquidity/capacity, corporate-action total return, or
   regime-dependent risk; results must not be presented as execution-grade or
   production-ready performance estimates. Deeper validation and execution realism
   are roadmap Phase 2/3 work, not current capabilities.
5. Full factor decomposition, portfolio optimization, multi-user access controls,
   derivatives, and real brokerage execution are out of scope.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite, Recharts |
| Backend | FastAPI, async SQLAlchemy, Pydantic |
| AI | AWS Bedrock; Ollama local and Cloud |
| Web research | Perplexity via OpenAI-compatible API |
| Database | SQLite with aiosqlite |
| Retrieval | ChromaDB and sentence-transformers |
| Market data | FMP stable endpoints with yfinance fallback |

For the current engineering architecture, APIs, data model, and environment variables,
see [`code_context.md`](../code_context.md).
