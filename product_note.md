# Product Note - Quant Agentic Trading System

An AI-powered paper-trading research platform. Not a real-money system. Primary AI runtime is AWS Bedrock (Claude Sonnet), with Ollama and Ollama Cloud options in the UI.

Date: 2026-06-19

---

## 1) Product Positioning

Quant combines:

1. Paper-trading portfolio operations
2. Market/fundamental data retrieval
3. AI-assisted research synthesis
4. Strategy simulation and risk analytics
5. User-curated knowledge base (documents + extracted theses)

The goal is decision support, not auto-execution.

---

## 2) Current Implementation Snapshot

### Market and portfolio

1. Real-time quote/profile/search/history with FMP-first and Yahoo fallback.
2. Paper-trading flows (deposit/withdraw/buy/sell) with server-side guards.
3. Holdings and portfolio summary with live mark-to-market.

### AI copilot

1. Multi-agent routing in chat:
	- advice mode (tool-equipped)
	- research mode (Perplexity-backed)
	- auto mode (orchestrator classifies intent)
2. Provider/model controls in UI for Bedrock, Ollama local, and Ollama Cloud.
3. Tool access includes quote, portfolio, screener history, thesis search, entity graph, principles search, and ARK raw-text search.

### Research library and extraction

1. Manual ingestion via file upload or paste text.
2. mbox ingestion support for newsletter/email imports.
3. SHA256 deduplication and document archive in DB + markdown files.
4. Post-ingest structured extraction:
	- theses (entity/theme/stance/claims/type)
	- entity relationships (supplier/customer/competitor-like edges)
5. Extraction provider/model can be selected (Bedrock/Ollama/Ollama Cloud).

### Retrieval/indexing

1. Principles retrieval:
	- corpus in `investing_research/`
	- semantic + keyword hybrid fusion
2. ARK raw-text retrieval:
	- separate corpus and index path
	- semantic with keyword fallback
3. Knowledge search endpoints currently reflect this split (`search` for principles, `search-ark` for ARK corpus).

### Screener and simulation

1. Value screener with six Buffett/Brealey/Shiller/Munger criteria.
2. Screener run history persisted for future agent context.
3. Backtesting and analytics include Sharpe/Sortino/Calmar, drawdown, alpha/beta, Monte Carlo, walk-forward split, and stress windows.

---

## 3) Current Constraints

1. ARK naming and ARK-specific service paths make multi-fund extension less clean.
2. Perplexity outputs are available for live chat but not yet persisted as first-class knowledge documents.
3. Principles and market-opinion metadata are not fully separated in DB schema.
4. Existing DB lifecycle uses `create_all`; schema evolution requires explicit migration scripts.

---

## 4) Target Design (Planned)

### Core design principle

Adopt a two-lane knowledge architecture:

1. Principles lane (manual-only, evergreen)
2. Market-opinion lane (fund letters + optional Perplexity sentiment/context, time-sensitive)

### Source expansion

Support multiple fund opinion sources without source-specific branching:

1. ARK
2. GMO
3. Sequoia
4. Bridgewater
5. Additional funds over time

### Perplexity role

Perplexity is used as a controlled market-context layer:

1. Optional persistence of research outputs
2. Citation/provenance stored
3. TTL on time-sensitive entries to avoid stale sentiment contamination

### Retrieval policy

Agent reasoning should follow hierarchy:

1. Principles first (framework)
2. Fund opinions second (manager theses)
3. Web sentiment/context third (time-sensitive)

Responses should always surface source + date and distinguish fact vs forecast/opinion.

---

## 5) Product Workflow Decision

Recommended operating model: hybrid.

1. Keep fund-letter ingestion manual for quality control and conviction building.
2. Add Perplexity persistence for timely sentiment and macro context.
3. Keep principles manual-only.
4. Periodically prune stale market-context entries via TTL cleanup.

This balances high signal quality with faster market awareness.

---

## 6) Build Direction

1. Generalize ARK-specific naming in services/tools/endpoints to source-agnostic market-opinion naming.
2. Add taxonomy metadata to documents/theses:
	- corpus
	- source_type
	- fund
	- recency/expiration
	- reliability tier
3. Add Perplexity ingest endpoint and indexing path.
4. Implement using one market-opinion vector collection with metadata filters.
5. Perplexity ingestion is manually triggered in the first implementation; scheduling is optional later.

Detailed implementation context is tracked in `research_workflow_change_spec.md`.

---

## 7) Known Constraints and Risks

### Data and infra

1. FMP free-tier request limits and coverage constraints remain.
2. EOD data only (no intraday strategy support).
3. Some fundamentals can be sparse or lagged depending on fallback source.

### AI and extraction

1. Extraction quality depends on provider/model and prompt alignment.
2. Very long documents may be truncated during extraction.
3. Over-automation risk: stale sentiment can degrade answer quality if TTL and provenance are not enforced.

### Quant analytics scope

1. Full factor decomposition and portfolio-optimization stacks are still out of current scope.
2. Transaction-cost and slippage realism remains simplified in backtests.

---

## 8) Technology Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Pydantic |
| AI (primary) | AWS Bedrock |
| AI (additional) | Ollama local, Ollama Cloud |
| Research web specialist | Perplexity via OpenAI-compatible endpoint |
| Database | SQLite + aiosqlite |
| Semantic retrieval | chromadb + sentence-transformers (all-MiniLM-L6-v2) |
| Market data | FMP stable endpoints + yfinance fallback |
| Frontend | React, TypeScript, Vite, Recharts |
