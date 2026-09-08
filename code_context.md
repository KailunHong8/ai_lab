# Code Context

Last verified: 2026-07-11

This is the canonical as-built engineering reference for Quant. Update it when
routes, services, data models, environment variables, or infrastructure change.

- Frontend: React, TypeScript, Vite.
- Backend: Python and FastAPI.
- GitHub repo: https://github.com/KailunHong8/quant

---

## Architecture

```
AI_lab_standalone/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, router registration, lifespan
│   ├── db.py                    # Async SQLAlchemy engine + SessionLocal
│   ├── models.py                # Portfolio, knowledge, screener, and chat-session ORM models
│   ├── routers/
│   │   ├── agent.py             # POST /api/agent/chat — advice, research, and auto modes
│   │   ├── knowledge.py         # Research ingestion, retrieval, reindexing, and stale cleanup
│   │   ├── market.py            # FMP quotes, profiles, search, history
│   │   ├── portfolio.py         # Paper trading: deposit/withdraw/buy/sell/holdings/summary
│   │   ├── screener.py          # Value screen: FMP fundamentals + yfinance fallback + thesis enrichment
│   │   ├── simulation.py        # Backtest: rule-based + Monte Carlo + walk-forward + stress tests
│   │   └── sessions.py          # Persistent named copilot sessions
│   └── services/
│       ├── bedrock.py           # AWS Bedrock agentic chat (tool-use loop)
│       ├── ollama_client.py     # Ollama local LLM (same tool interface as Bedrock)
│       ├── orchestrator.py      # Auto-mode intent classification
│       ├── perplexity_client.py # Web-research provider client
│       ├── research.py          # Principles retrieval over investing_research/
│       ├── market_opinion_research.py # Shared fund-letter and web-research retrieval
│       ├── knowledge_base.py    # Thesis + entity graph queries from SQLite
│       ├── thesis_extractor.py  # LLM-based structured extraction from uploaded docs
│       ├── fmp.py               # FMP API client with TTL caching + Yahoo fallback
│       └── yahoo.py             # Yahoo Finance connector (fallback)
├── frontend/src/
│   ├── App.tsx                  # Routes
│   ├── components/Layout.tsx    # Nav bar
│   ├── pages/
│   │   ├── Agent.tsx            # Chat copilot with provider/model selector
│   │   ├── Research.tsx         # Document upload with provider/model selector
│   │   ├── Screener.tsx         # Value screener UI
│   │   ├── Simulation.tsx       # Strategy sim: equity curve, Monte Carlo, walk-forward, stress tests
│   │   ├── Dashboard.tsx
│   │   ├── Holdings.tsx
│   │   ├── Transactions.tsx
│   │   └── Market.tsx
│   └── api/client.ts            # Axios wrappers for all endpoints
├── investing_research/          # PDF/MD books (Brealey, Shiller, Munger)
├── knowledge_base/documents/    # Parsed research docs (markdown)
├── chroma_principles/           # chromadb persistent index (auto-created)
├── chroma_market_opinion/       # Shared market-opinion index (auto-created)
├── change_specs/                # Product note, dated change specs, and archives
├── screener_scripts/            # Standalone analysis scripts (not part of the app)
│   ├── value_investing_screener.py
│   ├── market_scanner_full.py
│   └── comprehensive_analysis_enhanced.py
└── quant.db                     # SQLite database
```

---

## API Surface

| Area | Router prefix | Key capabilities |
|---|---|---|
| Market | `/api/market` | Quote, profile, symbol search, and EOD history |
| Portfolio | `/api/portfolio` | Deposit, withdraw, buy, sell, holdings, summary, and transactions |
| Agent | `/api/agent` | Copilot chat with advice, research, or automatic routing |
| Sessions | `/api/sessions` | Create, list, rename, delete, and read persistent chat sessions |
| Knowledge | `/api/knowledge` | Upload, Perplexity ingestion, documents, theses, entity graph, principles and market-opinion search, reindexing, stale cleanup |
| Screener | `/api/screener` | Value-screen runs, history, and model options |
| Simulation | `/api/simulation` | Strategy parsing, single-ticker runs, and portfolio runs |

## Knowledge Model

`Document` and `Thesis` records carry taxonomy metadata. The two supported corpora are:

1. `principles`: manual, evergreen investing frameworks retrieved from
   `investing_research/`.
2. `market_opinion`: fund letters and Perplexity web research, retrieved from one
   shared Chroma collection with `fund` and `source_type` filters.

Perplexity ingestion is manually triggered through
`POST /api/knowledge/ingest-perplexity`. It stores citation and expiration metadata;
web-research entries receive a 30-day TTL. Existing databases require
`scripts/migrate_taxonomy.py` because the application startup still uses `create_all`.

---

## FMP API Reference

Primary market data source. All endpoints use `/stable/` base URL.

- **Base URL**: `https://financialmodelingprep.com/stable`
- **Auth**: `apikey` query parameter
- **Docs**: https://site.financialmodelingprep.com/developer/docs/
- **Free tier**: ~250 req/day; 402/403 on restricted endpoints → fall back to Yahoo Finance

### Key Endpoints Used

| Purpose | Endpoint |
|---|---|
| Real-time quote | `GET /stable/quote?symbol=AAPL` |
| Company profile | `GET /stable/profile?symbol=AAPL` |
| Symbol search | `GET /stable/search-name?query=apple` |
| Historical OHLCV | `GET /stable/historical-price-eod/full?symbol=AAPL&from=YYYY-MM-DD&to=YYYY-MM-DD` |
| Key ratios (screener) | `GET /stable/ratios?symbol=AAPL&limit=1` |

---

## AI Provider Pattern

The agent supports Bedrock, local Ollama, and Ollama Cloud. `orchestrator.py` selects
advice or Perplexity-backed research in automatic mode. The agent's common tools cover
quotes, the paper portfolio, theses, entity relationships, screener history, principles,
and market-opinion retrieval.

`bedrock.py` and `ollama_client.py` share tool dispatch. The system prompt instructs
the agent to reason from principles first, fund opinions second, and time-sensitive web
context last; it must label sources and distinguish facts from forecasts.

For document extraction, `thesis_extractor.extract_and_save(..., provider, model)`
routes to the selected provider.

---

## Semantic Search

- Principles use persistent ChromaDB at `chroma_principles/` with
  `all-MiniLM-L6-v2`; keyword overlap is the dependency-free fallback.
- Fund letters and web research use the shared `market_opinion` ChromaDB collection at
  `chroma_market_opinion/`, with metadata filters rather than per-fund indexes.
- Reindex principles with `POST /api/knowledge/reindex`; reindex market opinions with
  `POST /api/knowledge/reindex-market`; `REBUILD_INDEX=1` rebuilds the principles index
  at startup.

---

## Simulation Analytics

The simulation router computes:
- **Core**: Sharpe, Sortino, Calmar, annualised return, max/avg drawdown, beta, Jensen's alpha, momentum flag.
- **Monte Carlo**: bootstrap resampled paths, P5/P25/P50/P75/P95 fan, probability of profit.
- **Walk-forward**: 70/30 split, overfit warning (IS profitable + OOS loss).
- **Stress tests**: strategy replayed over 2008 GFC, 2020 COVID, 2022 rate shock windows.
- All analytics are computed in pure Python (no numpy/scipy required); scipy is installed but not used in the hot path.

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `FMP_API_KEY` | — | FMP market data |
| `BEDROCK_REGION` | `eu-west-1` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | `eu.anthropic.claude-sonnet-4-6` | Bedrock model |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:9b` | Default Ollama model |
| `OLLAMA_CLOUD_MODEL` | `gpt-oss:120b` | Default Ollama Cloud model |
| `OLLAMA_API_KEY` | — | Ollama Cloud API key |
| `PERPLEXITY_BASE_URL` | `http://127.0.0.1:8045/v1` | Perplexity-compatible endpoint |
| `PERPLEXITY_API_KEY` | — | Perplexity-compatible endpoint API key |
| `PERPLEXITY_MODEL` | `claude45sonnetthinking` | Perplexity research model |
| `DATABASE_URL` | `sqlite+aiosqlite:///./quant.db` | Database connection string |
| `REBUILD_INDEX` | — | Set to `1` to force chromadb re-index on startup |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | — | Enable optional LLM tracing |
