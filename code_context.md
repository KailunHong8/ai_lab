# Code Context

- We use React (TypeScript, Vite) for the frontend and Python/FastAPI for the backend.
- GitHub repo: https://github.com/KailunHong8/quant
- Always update documentation (markdown files) in the repo to reflect the latest changes.

---

## Architecture

```
AI_lab/
├── backend/
│   ├── main.py                  # FastAPI app, CORS, router registration, lifespan
│   ├── db.py                    # Async SQLAlchemy engine + SessionLocal
│   ├── models.py                # ORM models: User, Position, Transaction, Document, Thesis, Entity, EntityRelationship
│   ├── routers/
│   │   ├── agent.py             # POST /api/agent/chat — provider/model toggle (Bedrock|Ollama)
│   │   ├── knowledge.py         # Research library CRUD + semantic search + reindex
│   │   ├── market.py            # FMP quotes, profiles, search, history
│   │   ├── portfolio.py         # Paper trading: deposit/withdraw/buy/sell/holdings/summary
│   │   ├── screener.py          # Value screen: FMP fundamentals + yfinance fallback + thesis enrichment
│   │   └── simulation.py        # Backtest: rule-based + Monte Carlo + walk-forward + stress tests
│   └── services/
│       ├── bedrock.py           # AWS Bedrock agentic chat (tool-use loop)
│       ├── ollama_client.py     # Ollama local LLM (same tool interface as Bedrock)
│       ├── research.py          # Semantic search over investing_research/ via chromadb
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
├── screener_scripts/            # Standalone analysis scripts (not part of the app)
│   ├── value_investing_screener.py
│   ├── market_scanner_full.py
│   └── comprehensive_analysis_enhanced.py
└── quant.db                     # SQLite database
```

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

Both `bedrock.py` and `ollama_client.py` expose the same `chat(message, history, portfolio_snapshot, model)` signature. The router decides which to call based on the `provider` field in the request body.

Tool dispatch (`_dispatch_tool`) is shared — ollama_client imports it from bedrock.py.

For document extraction, `thesis_extractor.extract_and_save(..., provider, model)` routes to `ollama_client.extract_json` or `bedrock._call_bedrock`.

---

## Semantic Search

- Library: chromadb (persistent, `chroma_principles/`) + sentence-transformers (`all-MiniLM-L6-v2`, ~80MB, CPU).
- Fallback: keyword overlap (no dependencies) if chromadb is not installed.
- Re-index: `POST /api/knowledge/reindex` or set `REBUILD_INDEX=1` env var on startup.
- Called by: the `search_principles` tool in the agent, and the `/api/knowledge/search` endpoint.

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
| `REBUILD_INDEX` | — | Set to `1` to force chromadb re-index on startup |
