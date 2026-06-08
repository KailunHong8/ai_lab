# Product Note — Quant Agentic Trading System

An AI-powered paper-trading research platform. Not a real-money system. Powered by AWS Bedrock (Claude Sonnet 4.6) with Ollama as a local fallback.

---

## Core Features

### Market Data
- Real-time quotes, company profiles, symbol search, and EOD historical prices via FMP free tier (`/stable/` endpoints).
- Yahoo Finance as automatic fallback when FMP returns 402/403/404.
- FMP API key: configured via `FMP_API_KEY` env var (free tier: ~250 req/day).

### Portfolio (paper trading)
- Cash deposit / withdrawal (guards against overdraft).
- Buy/sell shares with real-time prices (guards against buying more than cash, selling more than held).
- Holdings with P&L, portfolio summary (total value, return %), full transaction history.

### AI Trading Copilot
- Agentic loop: grounded in investing principles (Brealey-Myers, Shiller, Poor Charlie's Almanack) via semantic search, layered with user-uploaded research (ARK etc.).
- Tools: `get_quote`, `get_portfolio`, `search_theses`, `get_entity_graph`, `search_principles`.
- **Provider toggle**: Bedrock (Claude Sonnet 4.6) or Ollama (local, e.g. qwen2.5:9b) selectable per session from the UI.
- Model selector in the UI dropdown for both providers.

### Research Library
- Upload PDFs, text, markdown, or Gmail `.mbox` exports.
- LLM extracts structured investment theses (entity, stance, claims, type) and entity relationships (supplier/customer/competitor graph).
- **Provider toggle on upload**: choose Bedrock or Ollama for thesis extraction.
- SHA256 dedup prevents duplicate imports; mbox imports split individual emails.
- Semantic search over documents via `POST /api/knowledge/search`.
- Force re-index: `POST /api/knowledge/reindex`.

### Value Screener
- Screen any comma-separated watchlist against 6 Buffett/Brealey/Shiller/Munger criteria.
- **Data source**: FMP `/stable/ratios` + profile first, yfinance fallback.
- Criteria: D/E ≤ 0.5, Current Ratio ≥ 1.5, P/B ≤ 2.0, ROE ≥ 10%, ROA ≥ 5%, Interest Coverage ≥ 4×.
- Passing stocks enriched with ARK research theses from the knowledge base + principles snippet.
- Configurable minimum criteria threshold (default ≥ 4/6).

### Strategy Simulation (institutional-grade)
- Natural-language strategy description → LLM parses into executable rules.
- **Provider toggle**: Bedrock or Ollama for strategy parsing.
- Rule-based backtester (buy-on-dip, sell-on-gain/stop-loss/hold-days).
- **Institutional risk metrics**: Sharpe, Sortino, Calmar, annualised return, max drawdown, avg drawdown, beta vs benchmark, Jensen's alpha, 60-day momentum flag.
- **Monte Carlo simulation**: bootstrap resampling of daily returns, percentile fan chart (P5/P25/P50/P75/P95), probability of profit.
- **Walk-forward validation**: 70/30 in-sample / out-of-sample split with overfit warning.
- **Stress test overlays**: 2008 GFC, 2020 COVID crash, 2022 rate shock — runs the strategy over each period separately.
- Benchmark comparison: configurable (default SPY).

### Principles Library (semantic search)
- Investing books in `investing_research/` indexed via chromadb + sentence-transformers (all-MiniLM-L6-v2).
- Keyword fallback if chromadb is unavailable.
- Add a new book by dropping any PDF/MD/TXT into `investing_research/` and calling `POST /api/knowledge/reindex`.

---

## Known Constraints & Self-Critique

### Data limitations
- FMP free tier: ~250 req/day, no options/futures, limited international coverage.
- EOD data only — intraday/HFT strategies are not feasible and not supported.
- Fundamental ratios from FMP may lag 1 quarter (TTM).

### Analytics gaps (not yet implemented)
- **Factor decomposition**: true Fama-French 3/5-factor regression requires the FF factor data files (freely available from Ken French's website). Currently approximated via beta/alpha only.
- **Barra-style risk model**: requires covariance matrix from a factor library — out of scope for free-tier data.
- **Walk-forward over rolling windows**: currently a single 70/30 split; multi-window rolling WFO would require ≥3 years of data per symbol.
- **Correlation / portfolio-level simulation**: all simulations are single-asset; multi-asset portfolio optimisation (Markowitz efficient frontier) is not yet implemented.
- **Transaction costs / slippage**: backtester assumes zero transaction cost and perfect fill at close — results will overstate real-world performance.
- **Survivorship bias**: screener uses the user's provided watchlist; there is no guard against screener lists that exclude delisted stocks.
- **vectorbt integration**: deferred — the pure-Python backtester covers the current use case; vectorbt would add vectorised multi-strategy sweeps if needed.

### AI / LLM limitations
- Strategy parser is only as good as the model and the prompt; complex conditional strategies (e.g. "buy when RSI < 30 AND volume spike") may not parse correctly.
- Ollama tool-use quality varies by model; qwen2.5:9b is the tested baseline.
- Thesis extraction truncates documents to 12k characters — long reports lose tail content.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Pydantic |
| AI (primary) | AWS Bedrock — Claude Sonnet 4.6 |
| AI (fallback) | Ollama — qwen2.5:9b (local) |
| Database | SQLite + aiosqlite |
| Semantic search | chromadb + sentence-transformers (all-MiniLM-L6-v2) |
| Market data | FMP `/stable/` + yfinance fallback |
| Frontend | React, TypeScript, Vite, Recharts |
| Screener data store | yfinance (from-memory, no ArcticDB dependency in the app) |
