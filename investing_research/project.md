---

# Project Overview

AI-powered paper-trading and strategy research platform. Users interact via a React UI backed by a FastAPI service. An agent on the AI Model Router (AWS Bedrock as fallback) acts as the trading copilot, grounding its reasoning in research documents stored in `investing_research/` and live market data from the FMP free-tier API.

GitHub repo: https://github.com/KailunHong8/quant

## Development Commands

### Backend

```bash
# From repo root — run with the backend package in scope
cd /path/to/AI_lab
source venv/bin/activate
uvicorn backend.main:app --reload
```

The backend runs on `http://localhost:8000`. The `--reload` flag watches for file changes.

### Frontend

```bash
cd frontend
npm install       # first time only
npm run dev       # Vite dev server on http://localhost:5173
npm run build     # TypeScript check + production build
npm run lint      # ESLint
```

### Environment

Copy `.env.example` to `.env` and fill in values. The backend loads `.env` via `python-dotenv` at startup.

Required variables:
- `FMP_API_KEY` — Financial Modeling Prep API key
- `AI_MODEL_ROUTER_BASE_URL` / `AI_MODEL_ROUTER_API_KEY` / `AI_MODEL_ROUTER_MODEL` — hosted LLM (primary)
- `BEDROCK_REGION` / `BEDROCK_MODEL_ID` — AWS Bedrock (fallback; defaults: `eu-west-1` / `anthropic.claude-sonnet-4-20250514-v1:0`)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — AWS credentials for Bedrock (Account ID: 100927400432)
- `DATABASE_URL` — SQLite default: `sqlite+aiosqlite:///./quant.db`

## Architecture

### Backend (`backend/`)

FastAPI app with four routers, all under `/api/`:

| Router | Prefix | Responsibility |
|---|---|---|
| `routers/market.py` | `/api/market` | FMP proxy — quotes, profiles, history, search |
| `routers/portfolio.py` | `/api/portfolio` | Paper-trading CRUD — deposit/withdraw/buy/sell, holdings, summary, transactions |
| `routers/agent.py` | `/api/agent` | Agentic chat (router/Bedrock), session management |
| `routers/simulation.py` | `/api/simulation` | Backtesting — NL strategy → rule set → replay on OHLCV |

**Services:**
- `services/fmp.py` — `httpx` async client against `https://financialmodelingprep.com/stable`
- `services/llm_client.py` — hosted LLM client (AI Model Router, Bedrock fallback) with tool-use loop (`get_quote`, `get_portfolio`, `search_research`)
- `services/research.py` — Lazy-loads and chunks PDFs + markdown from `investing_research/` (500-word windows, keyword-overlap retrieval)

**Database:** SQLAlchemy async (aiosqlite for SQLite). Schema: `User`, `Position`, `Transaction`. `init_db()` is called on startup via FastAPI `lifespan`. Single-user; the default user is auto-created.

**Key invariants enforced server-side only:**
- Buy: `shares × price ≤ cash_balance`
- Sell: `shares_to_sell ≤ position.shares`
- Withdraw: `amount ≤ cash_balance`

### Frontend (`frontend/`)

React 19 + TypeScript, Vite, Tailwind CSS, React Router v7, Recharts.

All API calls go through `src/api/client.ts` — a single Axios instance pointing at `http://localhost:8000`.

Pages map to three workspaces, each with local views:
- `/portfolio` → Portfolio (overview, positions, activity)
- `/research/library` → Research (library, company, discover)
- `/strategies` → Strategies
- `/agent` → AI Copilot (reached from the "Ask AI" header action)
- `/simulation` → legacy backtest view, kept for compatibility

### Research Corpus

`investing_research/` holds the two finance textbooks (Shiller, Brealey-Myers-Allen PDFs) plus `context.md`. `services/research.py` indexes them at first call and caches in memory. Adding files to `investing_research/` automatically makes them searchable by the agent.

## FMP API Notes

Base URL: `https://financialmodelingprep.com/stable`

Free tier has ~250 req/day and may return 402/403 on some endpoints. Yahoo Finance is used as a fallback where needed. Key endpoints:
- `GET /stable/quote?symbol=AAPL` — real-time quote
- `GET /stable/profile?symbol=AAPL` — company profile
- `GET /stable/historical-price-eod/full?symbol=AAPL&from=...&to=...` — OHLCV for backtesting
- `GET /stable/search-name?query=apple` — symbol search

## AWS Bedrock Configuration (legacy fallback)

- **Account ID:** 100927400432
- **IAM User:** BedrockUser
- **Region:** eu-west-1
- **Model:** anthropic.claude-sonnet-4-20250514-v1:0 (or similar Sonnet 4 variant)
- **Pricing:** ~$3/1M input tokens, ~$15/1M output tokens
