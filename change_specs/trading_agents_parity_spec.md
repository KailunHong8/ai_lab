# Change Spec — Multi-Agent Trading Intelligence (TradingAgents Parity)

**Date:** 2026-08-31
**Status:** Proposed
**Author perspective:** Google Principal Architect
**Source reference:** TradingAgents (TauricResearch/TradingAgents, CC BY 4.0)
**Revision:** 2 — addresses data-source strategy, feasibility gate, and rebuild scope

---

## 1. Strategic Context

Quant was built iteratively without a clear end-state, accumulating FMP API
dependencies, a complex ChromaDB research library, and a single-agent copilot
that routes to Perplexity. Perplexity access is gone. FMP is paywalled for
most useful data. The result is a system that costs money for limited data,
is hard to reason about, and doesn't deliver the multi-agent intelligence that
is the actual goal.

This spec defines a **rebuild toward TradingAgents.ai parity** using only free
data sources and the LLM providers already in use (Bedrock, Ollama). The north-
star user outcome from the original spec stands:

> A user names a ticker and a date. Quant runs four specialist analysts in
> parallel, conducts a structured bull/bear debate, applies risk controls
> against the live portfolio, and presents a typed trade proposal with full
> evidence lineage before any paper order is submitted.

The rebuild also adds an **MCP server** so Quant's analysis tools are available
as Claude/AI tool calls — the same backend serves the web UI and AI assistants.

---

## 2. Feasibility Gate — Free APIs vs. Alpha Vantage

The question: can we reach TradingAgents-parity data quality using only free
APIs? If yes at >80% confidence, skip Alpha Vantage entirely.

### Free data stack evaluation

| Data need | Free option | Quality assessment |
|---|---|---|
| OHLCV price history | **yfinance** — no API key, no rate limit | 100% — covers US + global, splits-adjusted, reliable |
| Technical indicators | **pandas_ta** on yfinance OHLCV — pure Python, zero API calls | 100% — RSI, MACD, BBANDS, SMA, EMA all computable locally |
| Company fundamentals | **yfinance** `.info`, `.income_stmt`, `.balance_sheet`, `.cash_flow` | 90% — P/E, EPS, revenue, margins, debt/equity; sparse for micro-caps |
| Real-time quote | **yfinance** | 95% — 15-min delayed but sufficient for daily-bar analysis |
| Earnings calendar | **yfinance** `.calendar` + **Finnhub** `/earnings-calendar` (free tier) | 90% |
| Company news | **yfinance** `.news` (articles, timestamps) + **Finnhub** `/company-news` | 90% — good coverage, US-focused |
| News sentiment score | **Finnhub** `/news-sentiment` (free tier, 60 calls/min) | 80% — aggregate score + article-level buzz/sentiment metrics |
| Macroeconomic data | **FRED** — free, API key required but free to obtain | 100% — authoritative source, no rate limit concern |
| Research synthesis | LLM (Bedrock/Ollama) reasoning over the above data | 85% — no web search, but analyst reports are self-contained |

**Verdict: 88% feasibility. Do not use Alpha Vantage API.**

What we lose vs. Alpha Vantage paid:
- Pre-computed AV sentiment scores (replaced by Finnhub + LLM synthesis)
- AV intraday data (not needed for daily-bar strategy)
- AV's StockTwits/Reddit raw feed (StockTwits now requires auth; Reddit adds
  OAuth friction; the signal is noisy — skip both for a hobby project)

What we also lose:
- Perplexity (gone — replaced by LLM synthesis of structured data)

The Finnhub free tier (60 calls/min) and FRED are the only new API keys needed.
yfinance and pandas_ta are zero-configuration.

---

## 3. Rebuild Scope

The existing Quant codebase is the starting point, not the constraint.

**Keep:** FastAPI, SQLite + async SQLAlchemy, Bedrock/Ollama integration,
paper portfolio concept, strategy simulation engine (use as the trade
execution and performance tracking layer).

**Replace:**
- FMP API → yfinance + Finnhub (free, no paywall)
- Perplexity → removed (gone)
- ChromaDB + complex research library → simplified in-memory context
  assembly (the multi-agent system assembles evidence per-run, not via a
  standing vector store; a lightweight vector index can be reintroduced in
  a later phase if needed)
- Single-agent copilot → multi-agent pipeline (described below)
- Overly complex knowledge ingestion workflow → streamlined

**Add:**
- Free data clients (yfinance wrapper, Finnhub client, FRED client)
- Technical indicator computation (pandas_ta, no API)
- Multi-agent orchestrator with specialist analysts
- Bull/Bear debate layer
- Risk Manager + Portfolio Manager agents
- Decision memory with realized-return reflection
- MCP server exposing Quant's tools

---

## 4. Architecture

### 4.1 System Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Clients                                                     │
│  ┌──────────────────┐    ┌─────────────────────────────┐   │
│  │   React Web UI    │    │  Claude Code / AI assistant  │   │
│  │ (existing + new   │    │  (via MCP server)            │   │
│  │  proposal card)   │    │                              │   │
│  └────────┬─────────┘    └──────────────┬──────────────┘   │
└───────────┼───────────────────────────── ┼──────────────────┘
            │ REST                          │ MCP (stdio/HTTP)
┌───────────▼───────────────────────────── ▼──────────────────┐
│  Backend (FastAPI)                                           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Multi-Agent Orchestrator                            │   │
│  │  Phase 1: parallel analyst fan-out                  │   │
│  │  Phase 2: bull/bear debate                          │   │
│  │  Phase 3: trader synthesis                          │   │
│  │  Phase 4: risk gate (deterministic + LLM commentary)│   │
│  └──────────┬─────────────┬──────────────┬────────────┘   │
│             │             │              │                   │
│  ┌──────────▼──┐  ┌───────▼──────┐  ┌───▼──────────────┐  │
│  │ Fundamentals│  │  Technical   │  │  Sentiment/News  │  │
│  │  Analyst    │  │  Analyst     │  │  Analyst         │  │
│  └──────────┬──┘  └───────┬──────┘  └───┬──────────────┘  │
│             │             │              │                   │
│  ┌──────────▼─────────────▼──────────────▼───────────────┐ │
│  │  Data Layer                                            │ │
│  │  yfinance │ pandas_ta │ Finnhub │ FRED │ SQLite cache  │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Paper Portfolio + Decision Memory (SQLite)         │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 New File Tree

```
backend/
  services/
    market_data.py          ← unified interface over yfinance + Finnhub
    indicators.py           ← pandas_ta wrappers (RSI, MACD, BBANDS, SMA)
    fred.py                 ← FRED macro snapshot
    analyst/
      fundamentals.py       ← Fundamentals analyst agent
      technical.py          ← Technical analyst agent
      sentiment.py          ← Sentiment/news analyst agent
    debate/
      bull.py               ← Bull researcher
      bear.py               ← Bear researcher
    trader.py               ← Trader agent
    risk_manager.py         ← Risk manager (deterministic checks + LLM commentary)
    multi_agent.py          ← Orchestrator
    decision_memory.py      ← Decision log + reflection
  routers/
    agent.py                ← add /multi-run endpoint (keep existing /chat)
  mcp_server.py             ← MCP server (FastMCP or mcp-python-sdk)

frontend/src/
  pages/Agent.tsx           ← add multi-agent run button + proposal card
  components/ProposalCard.tsx ← new
```

---

## 5. Data Layer

### 5.1 `backend/services/market_data.py`

Single import point for all price/fundamental/news data. Internally uses yfinance
as primary, Finnhub as supplement. No callers need to know which source answered.

```python
# Interface contract
async def get_quote(symbol: str) -> Quote
async def get_profile(symbol: str) -> CompanyProfile
async def get_fundamentals(symbol: str) -> Fundamentals
    # yields: P/E, EPS, revenue TTM, gross margin, debt/equity,
    #         earnings surprise, next earnings date
async def get_price_history(symbol: str, period: str = "1y") -> pd.DataFrame
    # OHLCV, adjusted; period = "1y" | "2y" | "5y"
async def get_news(symbol: str, limit: int = 30) -> list[NewsItem]
    # merged from yfinance + Finnhub, deduped by headline similarity
async def get_news_sentiment(symbol: str) -> SentimentScore
    # Finnhub aggregate: bullish_pct, bearish_pct, score, article_count
```

SQLite-backed cache (table `data_cache`) with TTL per data type:
- Quotes: 60s
- Fundamentals: 24h
- Price history: 1h
- News: 2h
- News sentiment: 4h

### 5.2 `backend/services/indicators.py`

Computes technical indicators from a price DataFrame (no API calls):

```python
def compute_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series
def compute_macd(df: pd.DataFrame) -> pd.DataFrame  # MACD, signal, histogram
def compute_bbands(df: pd.DataFrame, period: int = 20) -> pd.DataFrame
def compute_sma(df: pd.DataFrame, periods: list[int] = [50, 200]) -> pd.DataFrame
def technical_summary(df: pd.DataFrame) -> TechnicalSnapshot
    # current RSI, MACD signal, price vs. SMA50/200, Bollinger position,
    # trend (up/down/sideways), momentum (strong/weak/diverging)
```

### 5.3 `backend/services/fred.py`

```python
MACRO_SERIES = {
    "fed_funds_rate": "FEDFUNDS",
    "cpi_yoy":        "CPIAUCSL",
    "unemployment":   "UNRATE",
    "yield_curve":    "T10Y2Y",
    "vix":            "VIXCLS",
}

async def get_macro_snapshot() -> MacroSnapshot
    # returns latest value + 3-month trend for each series
    # cached 24h in SQLite
```

Environment variable: `FRED_API_KEY` (free at fred.stlouisfed.org).

### 5.4 Finnhub client (inside `market_data.py`)

Environment variable: `FINNHUB_API_KEY` (free at finnhub.io, 60 calls/min).
Used for: company news, news sentiment scores, earnings calendar.
If key is not set, news falls back to yfinance-only and sentiment returns None.

---

## 6. Agent Layer

### 6.1 Analyst Agents

Each analyst receives `(symbol, analysis_date)` and returns a structured
`AnalystReport`. They are stateless — no shared mutable state, no DB writes.

#### Fundamentals Analyst
**Data fetched:** `get_fundamentals()`, earnings calendar, 3-year income/balance
sheet trend from yfinance.
**LLM task:** Assess valuation (P/E vs. sector), earnings quality, balance sheet
health, revenue trajectory, upcoming catalyst. Return structured summary + key
risks.
**Output fields:** `valuation_signal` (cheap/fair/expensive), `quality_signal`
(strong/neutral/weak), `catalyst`, `summary`, `key_risks`.

#### Technical Analyst
**Data fetched:** `get_price_history()` → `technical_summary()` (all computed
locally from pandas_ta, zero API calls).
**LLM task:** Interpret the technical snapshot. Trend direction, momentum
strength, key support/resistance levels, whether the setup is entry-worthy.
**Output fields:** `trend` (up/down/sideways), `momentum` (strong/weak/
diverging), `rsi`, `macd_signal`, `key_levels`, `summary`.

#### Sentiment/News Analyst
**Data fetched:** `get_news()`, `get_news_sentiment()`, `get_macro_snapshot()`.
**LLM task:** Aggregate news themes, interpret sentiment score, note macro
headwinds/tailwinds (yield curve, VIX regime, Fed rate direction).
**Output fields:** `news_tone` (positive/neutral/negative), `top_themes`,
`sentiment_score`, `macro_context`, `summary`.

Three analysts cover TradingAgents' four roles. News and Sentiment are merged
because they consume the same Finnhub/yfinance news feed — splitting them would
add a parallel call with no new data.

### 6.2 Researcher Agents (Bull/Bear)

Receive the three analyst reports as structured input. Do not fetch data.

**Bull researcher:** Reads all reports. Constructs the strongest bullish thesis:
leads with the most compelling supporting metrics, acknowledges but rebuts key
risks.

**Bear researcher:** Reads all reports. Constructs the strongest bearish thesis:
leads with valuation, momentum, or macro headwinds, challenges the bull case.

Both return `ResearchCase(thesis, supporting_points: list[str], key_risk_acknowledged, confidence: LOW|MEDIUM|HIGH)`.

Configurable `debate_rounds` (1–3). In round 2+, each researcher receives the
opponent's prior case and produces a rebuttal. Default: 1 round (no rebuttal),
which covers 90% of the TradingAgents signal with half the LLM cost.

### 6.3 Trader Agent

Receives: analyst reports + bull case + bear case + portfolio snapshot.

**Task:** Weigh the evidence. Issue a typed `TraderDecision`:
```
action: BUY | SELL | HOLD
confidence: LOW | MEDIUM | HIGH
rationale: str  (2–3 sentences citing specific analyst evidence)
suggested_size_pct: float  (% of portfolio value; 0 for HOLD/SELL)
time_horizon: str  ("short" | "medium" | "long")
```

The trader does not enforce risk limits — that is the Risk Manager's job. The
trader maximizes decision quality; the risk manager maximizes portfolio safety.

### 6.4 Risk Manager

Two-layer design: deterministic Python checks first, LLM commentary second.

**Deterministic checks (application code, not LLM):**
```python
def check_risk(decision: TraderDecision, portfolio: PortfolioSnapshot) -> RiskFlags:
    flags = []
    if decision.action == "BUY":
        proposed_pct = decision.suggested_size_pct
        if proposed_pct > 20:
            flags.append(RiskFlag.CONCENTRATION_HIGH)
        if portfolio.sector_exposure(symbol) > 35:
            flags.append(RiskFlag.SECTOR_OVERWEIGHT)
        if portfolio.cash_pct < proposed_pct + 5:
            flags.append(RiskFlag.INSUFFICIENT_CASH)
    return flags
```

**LLM commentary:** Given the flags + portfolio context, generate a 2-sentence
risk commentary. The commentary is informational; the flags determine approval.

`approved = len([f for f in flags if f.severity == "block"]) == 0`

Blocking flags: CONCENTRATION_HIGH (>20%), INSUFFICIENT_CASH.
Warning flags (non-blocking): SECTOR_OVERWEIGHT.

### 6.5 Multi-Agent Orchestrator (`backend/services/multi_agent.py`)

```python
async def run(
    symbol: str,
    analysis_date: date,
    provider: str,
    model: str | None,
    session_id: str,
    db: AsyncSession,
    debate_rounds: int = 1,
) -> TradeProposalResult:

    # Phase 1: parallel
    fundamentals_r, technical_r, sentiment_r = await asyncio.gather(
        fundamentals_analyst.run(symbol, analysis_date, provider, model),
        technical_analyst.run(symbol, analysis_date, provider, model),
        sentiment_analyst.run(symbol, analysis_date, provider, model),
    )
    reports = [fundamentals_r, technical_r, sentiment_r]

    # Phase 2: debate (sequential by design — bear reads bull, bull reads bear)
    bull = await bull_researcher.run(symbol, reports, provider, model)
    bear = await bear_researcher.run(symbol, reports, provider, model)
    for _ in range(debate_rounds - 1):
        bull = await bull_researcher.rebut(bull, bear, provider, model)
        bear = await bear_researcher.rebut(bear, bull, provider, model)

    # Phase 3: trader
    portfolio = await get_portfolio_snapshot(db)
    decision = await trader_agent.run(symbol, reports, bull, bear, portfolio, provider, model)

    # Phase 4: risk gate
    prior_memory = await decision_memory.get_prior(db, symbol)
    risk = await risk_manager.run(symbol, decision, portfolio, prior_memory, provider, model)

    # Phase 5: persist
    proposal = await _save_proposal(db, ...)
    await decision_memory.record(db, proposal)
    return TradeProposalResult(proposal=proposal)
```

---

## 7. API Layer

### New REST endpoint

```
POST /api/agent/multi-run
{
  "symbol": "AAPL",
  "analysis_date": "2026-08-31",
  "session_id": "...",
  "provider": "bedrock",
  "model": null,
  "debate_rounds": 1
}

→ 200 OK (streaming SSE: progress events as each phase completes)
→ final event: full TradeProposalResult JSON
```

The response is streamed via Server-Sent Events so the frontend can animate
the phase stepper without polling. Each phase emits a `phase_complete` event
with the phase name and a preview of the output.

Existing `/api/agent/chat` is unchanged.

### MCP Server (`backend/mcp_server.py`)

Exposes Quant's capabilities as MCP tools so Claude Code (and any MCP-compatible
AI assistant) can invoke them directly:

```python
from fastmcp import FastMCP

mcp = FastMCP("Quant Trading Intelligence")

@mcp.tool()
async def analyze_ticker(symbol: str, date: str | None = None) -> TradeProposalResult:
    """Run full multi-agent analysis: fundamentals, technical, sentiment, bull/bear
    debate, risk gate. Returns a typed trade proposal."""

@mcp.tool()
async def get_quote(symbol: str) -> Quote:
    """Real-time stock quote (price, change, volume, market cap)."""

@mcp.tool()
async def get_fundamentals(symbol: str) -> Fundamentals:
    """Company fundamentals: P/E, EPS, revenue, margins, debt/equity."""

@mcp.tool()
async def get_macro_context() -> MacroSnapshot:
    """Current macroeconomic snapshot: Fed rate, CPI, yield curve, VIX."""

@mcp.tool()
async def get_portfolio_summary() -> PortfolioSnapshot:
    """Current paper portfolio: holdings, cash, total value, sector exposure."""

@mcp.tool()
async def get_decision_history(symbol: str | None = None) -> list[DecisionMemoryItem]:
    """Prior trade proposals and realized outcomes. Optionally filtered by symbol."""

@mcp.tool()
async def screen_stocks(min_pe: float | None, max_pe: float | None,
                        min_roe: float | None, sector: str | None) -> list[str]:
    """Screen for tickers matching value criteria. Returns list of symbols."""
```

The MCP server runs as a separate process or via `fastmcp run backend/mcp_server.py`.
It imports the same service functions as the FastAPI app — no duplication.

---

## 8. Decision Memory

After each multi-agent run, `decision_memory.py` records:
- symbol, action (BUY/SELL/HOLD), price at decision time
- links to the full proposal (all reports, debate, decision, risk assessment)

A background task runs on each new analysis for the same symbol and checks if
any prior decision has passed its 30-day horizon. If so:
1. Fetches current price via `market_data.get_quote()`
2. Computes realized return vs. SPY (both from yfinance)
3. Calls a reflection prompt: "Given this prior decision and the realized
   outcome, what was the analysis right about, and where did it fail?"
4. Stores the reflection text; injects it into the Risk Manager prompt on the
   next run for the same symbol

```python
class DecisionMemory(Base):
    id: str
    symbol: str
    action: str            # BUY | SELL | HOLD
    decision_date: date
    price_at_decision: float
    proposal_id: str       # FK → TradeProposal
    horizon_date: date     # decision_date + 30 days
    realized_return: float | None
    spy_return: float | None
    reflection: str | None
    reflected_at: date | None
```

---

## 9. Frontend

Minimal changes to the existing Agent page:

1. **Ticker input + "Analyze" button** — separate from the chat input. Triggers
   `POST /api/agent/multi-run`.

2. **Phase stepper** — shows: Analysts (3 parallel) → Debate → Trader → Risk.
   Each phase transitions spinner → checkmark via SSE events.

3. **ProposalCard component** — displays the full structured result:
   - Summary row: ticker, date, trader decision (BUY/SELL/HOLD), confidence,
     risk approved (green/red)
   - Collapsible sections: Fundamentals | Technical | Sentiment | Bull Case |
     Bear Case | Risk Assessment
   - Each section shows its data sources (e.g., "yfinance, FRED")
   - Action buttons: **"Add to Portfolio"** (pre-fills existing buy/sell flow),
     **"Dismiss"**

4. **Decision history tab** — list of prior proposals with realized returns (once
   available). Thin table: date, symbol, action, return vs. SPY.

The existing chat copilot interface is unchanged. Multi-agent is opt-in, not a
replacement.

---

## 10. Implementation Phases

### Phase A — Data Foundation (1 week)

Goals: replace FMP with free data stack; ensure every data need for the agents
is covered.

1. `backend/services/market_data.py` — yfinance + Finnhub unified client with
   SQLite cache
   → verify: fetch AAPL quote, fundamentals, news, sentiment score; cache hit
   on second call within TTL
2. `backend/services/indicators.py` — pandas_ta wrappers
   → verify: RSI, MACD, BBANDS computed from yfinance OHLCV for AAPL
3. `backend/services/fred.py` — macro snapshot
   → verify: T10Y2Y and VIX latest values returned
4. DB migration: add `data_cache` table
5. Add `FINNHUB_API_KEY` and `FRED_API_KEY` to `.env.example`
6. Remove or gut FMP dependency from the critical path (keep the file so
   existing simulation engine doesn't break, but no new code should import it)

**Acceptance:** All data needs for all three analyst agents are met with free
sources. No FMP, no Perplexity, no Alpha Vantage in the new data path.

### Phase B — Agent Pipeline (3–4 weeks)

1. `analyst/fundamentals.py`, `analyst/technical.py`, `analyst/sentiment.py`
   → verify: each returns a structured `AnalystReport` for AAPL with all
   required fields populated
2. `debate/bull.py`, `debate/bear.py`
   → verify: each produces a `ResearchCase` from mock analyst reports
3. `trader.py`, `risk_manager.py`
   → verify: trader returns typed decision; risk manager applies deterministic
   checks correctly (test: suggest 25% allocation → CONCENTRATION_HIGH flag)
4. `multi_agent.py` orchestrator
   → verify: end-to-end run for AAPL returns full `TradeProposalResult`
5. DB models: `TradeProposal`, `DecisionMemory` + migration
6. `POST /api/agent/multi-run` with SSE streaming
   → verify: SSE events arrive in phase order; final event has all fields

**Acceptance:** integration test covering the full pipeline with mocked LLM
responses. Risk gate deterministic checks covered by unit tests.

### Phase C — MCP Server + Frontend (1–2 weeks)

1. `backend/mcp_server.py` with FastMCP
   → verify: `mcp dev backend/mcp_server.py` lists all tools; `analyze_ticker`
   tool returns a valid result
2. Add to `.claude/settings.json` as a local MCP server so Claude Code can use
   Quant tools natively
3. Frontend: ticker input, phase stepper, ProposalCard, decision history tab
   → verify: full manual test — run analysis, see stepper animate, review
   proposal, approve → paper transaction linked to proposal_id
4. `decision_memory.py` reflection background task
   → verify: reflection generated and stored after a synthetic 30-day horizon
   test

---

## 11. Non-Goals

1. Alpha Vantage, FMP, or Perplexity API dependencies.
2. StockTwits or Reddit direct integrations (auth complexity, noisy signal,
   Finnhub news sentiment covers the requirement adequately).
3. LangGraph or any external orchestration framework (plain asyncio.gather
   is sufficient and already fits the stack).
4. Real brokerage execution.
5. Intraday or streaming data.
6. Multi-user tenancy.
7. Preserving the ChromaDB research library in its current form — it will be
   simplified or removed as the multi-agent system replaces its function.

---

## 12. Dependencies and Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| yfinance rate limiting / data gaps | Medium | Cache aggressively; log misses; tolerate None fields gracefully |
| Finnhub free tier: 60 calls/min | Low for hobby use | SQLite cache with 2–4h TTLs; graceful degradation if key not set |
| FRED free: no practical rate limit | Very low | None needed |
| LLM cost: ~7 calls per full run | Medium | Default to Bedrock Haiku for analysts; Sonnet only for trader + risk; estimated $0.05–0.15/run |
| SSE streaming complexity | Low | FastAPI `StreamingResponse` with asyncio.Queue; well-established pattern |
| FastMCP or mcp-python-sdk API stability | Low | Pin version; MCP server is thin wrapper, easy to update |
| yfinance `.income_stmt` field changes | Low | Map fields defensively with `.get()` fallbacks |

---

## 13. Acceptance Criteria (Phases A + B together)

1. A full multi-agent run for any liquid US ticker completes using only yfinance,
   Finnhub, FRED, pandas_ta, and Bedrock/Ollama — no FMP, no Perplexity, no
   Alpha Vantage.
2. All three analyst reports are populated with real data, not placeholder text.
3. The risk manager's `approved` field is set by deterministic Python checks,
   not by LLM output.
4. A `TradeProposal` row in SQLite links to its `ChatSession` and, after user
   confirmation, to its paper `Transaction`.
5. Risk gate unit tests pass: CONCENTRATION_HIGH fires at >20%; INSUFFICIENT_CASH
   fires when cash < proposed allocation + 5%; SECTOR_OVERWEIGHT fires at >35%.
6. The MCP server lists all tools and `analyze_ticker("AAPL")` returns a valid
   result when called from Claude Code.

---

## 14. Environment Variables (complete new set)

```bash
# LLM (existing)
BEDROCK_REGION=eu-west-1
BEDROCK_MODEL_ID=eu.anthropic.claude-sonnet-4-6
AWS_PROFILE=

OLLAMA_HOST=http://localhost:11434
OLLAMA_API_KEY=

# Data (new — all free)
FINNHUB_API_KEY=          # free at finnhub.io
FRED_API_KEY=             # free at fred.stlouisfed.org

# Database (existing)
DATABASE_URL=sqlite+aiosqlite:///./quant.db
```

FMP_API_KEY, PERPLEXITY_API_KEY, ALPHA_VANTAGE_API_KEY removed from `.env.example`.
