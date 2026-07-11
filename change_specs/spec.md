# Functional Specification — Quant Agentic Trading System

## Overview

An AI-powered paper-trading and strategy research platform. Users interact via a React UI backed by a FastAPI service. An AWS Bedrock agent (Claude Sonnet 4.6) acts as the trading copilot, grounding its reasoning in research documents stored locally and live market data from the FMP free-tier API.

---

## Tech Stack

- **Frontend:** React (TypeScript)
- **Backend:** Python / FastAPI
- **LLM / Agent:** AWS Bedrock — `anthropic.claude-sonnet-4-6` via Bedrock Converse API with tool use
- **Market data:** Financial Modeling Prep (FMP) free tier — API key managed via environment variable
- **Research corpus:** `docs/` directory (PDFs + markdown: Shiller, Brealey-Myers-Allen)
- **Persistence:** SQLite (dev) / PostgreSQL (prod) — users, portfolios, positions, transactions
- **Repo:** [github.com/KailunHong8/quant](https://github.com/KailunHong8/quant)

---

## Modules & Features

### 1. Market Data (FMP Integration)

**Endpoints consumed (free tier):**
- `GET /quote/{symbol}` — real-time/delayed quote
- `GET /profile/{symbol}` — company profile
- `GET /historical-price-full/{symbol}` — OHLCV history (used for simulation)
- `GET /search` — symbol search

**FastAPI routes exposed:**
- `GET /api/market/quote/{symbol}`
- `GET /api/market/profile/{symbol}`
- `GET /api/market/search?q={query}`
- `GET /api/market/history/{symbol}?from=YYYY-MM-DD&to=YYYY-MM-DD`

---

### 2. Portfolio Management

**Data model:**

- `User` — id, username, cash_balance, initial_deposit
- `Position` — user_id, symbol, shares, avg_cost
- `Transaction` — user_id, symbol, type (BUY/SELL/DEPOSIT/WITHDRAW), shares, price, timestamp

**FastAPI routes:**
- `POST /api/portfolio/deposit` — add cash; record DEPOSIT transaction
- `POST /api/portfolio/withdraw` — subtract cash; guard: reject if resulting balance < 0
- `POST /api/portfolio/buy` — buy shares; guard: reject if cost > cash_balance
- `POST /api/portfolio/sell` — sell shares; guard: reject if shares > position held
- `GET /api/portfolio/holdings` — list all open positions with current market value (calls FMP live)
- `GET /api/portfolio/summary` — total portfolio value, initial deposit, P&L (absolute + %)
- `GET /api/portfolio/transactions` — full transaction history, filterable by date / symbol

**Portfolio value calculation:**
```
total_value = cash_balance + Σ(position.shares × current_price)
pnl = total_value − initial_deposit
pnl_pct = pnl / initial_deposit × 100
```

---

### 3. Strategy Research Assistant (Bedrock Agent)

The agent is invoked via the Bedrock Converse API with a system prompt that injects:
1. Chunked excerpts from the research corpus (`docs/`) — retrieved via simple keyword search over pre-indexed chunks.
2. The user's current portfolio snapshot (from `/api/portfolio/summary`).
3. Any live market data the user is asking about (fetched from FMP on-the-fly as a tool call).

**Capabilities:**
- Explain concepts from Shiller / Brealey (CAPM, NPV, real options, risk-adjusted return) in the context of the user's portfolio.
- Suggest allocation and strategy ideas grounded in the research material.
- Answer "what if I buy X shares of Y?" type questions.

**FastAPI route:**
- `POST /api/agent/chat` — body: `{message: str, session_id: str}`; response: full agent reply

**Agent tools (Bedrock tool use):**
- `get_quote(symbol)` — calls FMP for real-time quote
- `get_portfolio()` — reads current holdings from DB
- `search_research(query)` — retrieves relevant chunks from `docs/`

---

### 4. Strategy Simulation (Backtesting)

Users define a strategy in plain English and the agent translates it into a rule set, which is then replayed against historical FMP prices.

**FastAPI route:**
- `POST /api/simulation/run` — body: `{strategy_description: str, symbol: str, start_date: str, end_date: str, initial_capital: float}`

**Flow:**
1. Agent interprets `strategy_description` into a parameterised rule set (buy/sell thresholds, holding period).
2. Backend fetches OHLCV history from FMP for the date range.
3. Rule engine replays trades day-by-day on the historical data.
4. Returns: equity curve, final P&L, number of trades, win rate, max drawdown.

**Response schema:**
```json
{
  "pnl": 1234.56,
  "pnl_pct": 12.3,
  "num_trades": 42,
  "win_rate": 0.6,
  "max_drawdown_pct": 8.4,
  "equity_curve": [{"date": "...", "value": 10000.0}]
}
```

---

### 5. React Frontend Pages

| Page | Route | Description |
|---|---|---|
| Dashboard | `/` | Portfolio summary card, P&L, cash balance |
| Holdings | `/holdings` | Table of open positions, live prices, unrealised P&L per position |
| Transactions | `/transactions` | Filterable transaction log |
| Market | `/market` | Symbol search + quote card + basic price chart |
| Agent | `/agent` | Chat interface — strategy research & Q&A |
| Simulation | `/simulation` | Simulation form + results chart (equity curve) |

---

## Guards & Validation

- **Buy guard:** `cost = shares × quote.price`; reject if `cost > user.cash_balance`
- **Sell guard:** reject if `shares_to_sell > position.shares`
- **Withdraw guard:** reject if `amount > user.cash_balance`
- All guards enforced server-side in FastAPI (never only on client).

---

## Project Structure

```
quant/
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── routers/
│   │   ├── market.py
│   │   ├── portfolio.py
│   │   ├── agent.py
│   │   └── simulation.py
│   ├── services/
│   │   ├── fmp.py               # FMP API client
│   │   ├── bedrock.py           # Bedrock Converse + tool-use
│   │   └── research.py          # docs/ chunking & retrieval
│   ├── models.py                # SQLAlchemy ORM models
│   └── db.py                    # DB session / init
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Holdings, Transactions, Market, Agent, Simulation
│   │   ├── components/          # PortfolioCard, PositionTable, ChatWindow, EquityCurveChart
│   │   └── api/                 # Axios client wrappers
│   └── package.json
├── docs/
│   ├── context.txt
│   ├── Finance and the Good Society - Shiller.pdf
│   └── brealey-principles-of-corporate-finance-evergreen-2025.pdf
├── .env.example
└── backend/requirements.txt
```

---

## Environment Variables

```
FMP_API_KEY=<your_fmp_key>
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your_key>
AWS_SECRET_ACCESS_KEY=<your_secret>
DATABASE_URL=sqlite:///./quant.db
```

---

## Out of Scope (v1)

- Real brokerage execution (no real money)
- Options / derivatives trading
- Multi-user auth (single-user paper trading account is sufficient for v1)
- Real-time streaming prices (polling is acceptable given FMP free tier limits)
