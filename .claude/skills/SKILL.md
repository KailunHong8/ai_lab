---
name: fmp-yfinance-financial-analysis
description: >
  Run technical and fundamental analysis on any stock, ETF, or index using
  FMP (Financial Modeling Prep) and yfinance. Use this skill whenever the user
  asks to analyze a ticker, build a financial analysis workflow, fetch historical
  prices, compute technical indicators (RSI, MACD, Bollinger Bands, SMA, EMA),
  retrieve fundamentals (P/E, EPS, revenue growth, P/B, ROE, ROA), screen stocks,
  or generate a combined market report.
  Also trigger when the user mentions "market data", "stock fundamentals",
  "technical indicators", "financial API", "quant analysis", "equity screener",
  or "S&P 500 analysis". Always read this skill before running any market data
  or screener operation — do NOT proceed without reading these instructions first.
argument-hint: <TICKER or ANALYSIS_TYPE>
allowed-tools: Read, Write, Bash
---

# FMP + yfinance Financial Analysis Skill

## Overview

This skill orchestrates technical and fundamental analysis workflows using the
project's backend services:

- **Primary data source**: FMP (`/stable/` REST API) — quotes, profiles, EOD history,
  ratios, fundamentals. TTL-cached: quotes 30s, profiles/history 1hr.
- **Fallback data source**: yfinance — automatically used when FMP returns 402/403
  (free-tier restriction) or when FMP returns empty data.
- **No MCP connector** — all data flows through the FastAPI backend at `http://localhost:8000`
  or via the 6 AI copilot tools registered in `backend/services/bedrock.py`.
- **No intraday data** on the free FMP tier — see the coverage caveat section below.

**AI copilot tools available** (call these in the agent loop):
| Tool | What it returns |
|------|----------------|
| `get_quote(symbol)` | Live price, change %, volume, market cap (FMP → yfinance fallback) |
| `get_portfolio()` | Paper-trading holdings, cash balance, equity value, P&L |
| `search_theses(entity, theme)` | Structured investment theses from uploaded research (ARK, newsletters) |
| `get_entity_graph(symbol)` | Supply chain, competitor, customer relationships |
| `get_screener_history(limit)` | Recent value screen runs with fundamentals and pass/fail results |
| `search_principles(query)` | Semantic search over Brealey-Myers-Allen, Shiller, Poor Charlie's Almanack |

---

## Step 1 — Identify the request type

Classify the user request into one of these modes:

| Mode | Trigger phrases |
|------|----------------|
| `technical` | "RSI", "MACD", "chart", "moving average", "Bollinger", "support", "indicators" |
| `fundamental` | "P/E", "earnings", "revenue", "valuation", "fundamentals", "EPS", "ROE", "P/B" |
| `combined` | "full analysis", "research report", "analyze [TICKER]", "what do you think of" |
| `screener` | "screen stocks", "find stocks with", "filter by", "best stocks for", "watchlist" |
| `historical` | "historical prices", "price history", "OHLCV", "backtesting data" |

If the mode is ambiguous, default to `combined`.

**Note on `technical` mode**: The backend has no server-side indicator endpoint on the
free FMP tier. Technical indicators must be computed from EOD OHLCV data returned by
`GET /api/market/history/{symbol}`. The computation recipes are in Step 2.

---

## Step 2 — Data fetching and tool routing

### Market data endpoints

```
GET /api/market/quote/{symbol}      → price, change, volume, marketCap (FMP → yfinance)
GET /api/market/profile/{symbol}    → sector, industry, mktCap, description, CEO, website
GET /api/market/history/{symbol}    → EOD OHLCV array, sorted oldest-first
    params: from_date=YYYY-MM-DD, to_date=YYYY-MM-DD
GET /api/market/search?q=...        → symbol/name search (FMP only, no yfinance fallback)
```

**OHLCV field names** (both FMP and yfinance fallback return the same schema):
```
date, open, high, low, close, volume   (_source: "fmp" or "yahoo")
```

Always fetch at least 90 trading days (≈130 calendar days) of history for meaningful
technical signals. Use 252 trading days (≈365 calendar days) for SMA200 and annual
return calculations.

---

### Technical indicators — compute from OHLCV

Pull EOD history, then compute with pandas. The screener scripts use `pandas_ta`
(available in the conda/venv environment); for inline computation use these formulas:

**RSI-14**
```python
import pandas as pd
closes = pd.Series([r["close"] for r in history])
delta = closes.diff()
gain = delta.clip(lower=0).rolling(14).mean()
loss = (-delta.clip(upper=0)).rolling(14).mean()
rs = gain / loss
rsi = 100 - (100 / (1 + rs))
rsi_current = rsi.iloc[-1]
```

**SMA-50 and SMA-200**
```python
sma50  = closes.rolling(50).mean().iloc[-1]
sma200 = closes.rolling(200).mean().iloc[-1]
```

**EMA-20 and EMA-50**
```python
ema20 = closes.ewm(span=20, adjust=False).mean().iloc[-1]
ema50 = closes.ewm(span=50, adjust=False).mean().iloc[-1]
```

**MACD (12/26/9)**
```python
ema12   = closes.ewm(span=12, adjust=False).mean()
ema26   = closes.ewm(span=26, adjust=False).mean()
macd    = ema12 - ema26
signal  = macd.ewm(span=9, adjust=False).mean()
hist    = macd - signal
macd_current   = macd.iloc[-1]
signal_current = signal.iloc[-1]
hist_current   = hist.iloc[-1]
```

**Bollinger Bands (20-period, 2σ)**
```python
sma20   = closes.rolling(20).mean()
std20   = closes.rolling(20).std()
upper   = (sma20 + 2 * std20).iloc[-1]
lower   = (sma20 - 2 * std20).iloc[-1]
mid     = sma20.iloc[-1]
```

**Interpret signals before presenting:**
- RSI > 70 → overbought; RSI < 30 → oversold; 40–60 → neutral
- Price > SMA200 → above long-term trend (bullish bias)
- MACD hist positive and rising → bullish momentum
- Price at/below lower Bollinger Band → potential mean-reversion zone
- Golden cross: SMA50 crosses above SMA200 → long-term bullish signal
- Death cross: SMA50 crosses below SMA200 → long-term bearish signal

---

### Fundamental analysis

Use the screener endpoint to fetch fundamentals for any ticker:

```
GET /api/screener/run?tickers=AAPL&min_criteria=1&enrich=false
```

**Available fundamental fields** (FMP `ratios` + `profile` primary, yfinance fallback):

| Field in response | FMP source field | yfinance source field | Notes |
|---|---|---|---|
| `pe_ratio` | `priceEarningsRatio` | `trailingPE` | Trailing P/E |
| `pb_ratio` | `priceToBookRatio` | `priceToBook` | Price-to-book |
| `roe` | `returnOnEquity` × 100 | `returnOnEquity` × 100 | % |
| `roa` | `returnOnAssets` × 100 | `returnOnAssets` × 100 | % |
| `debt_equity` | `debtEquityRatio` | `debtToEquity` ÷ 100 | Ratio |
| `current_ratio` | `currentRatio` | `currentRatio` | |
| `interest_coverage` | `interestCoverageRatio` | EBITDA ÷ (totalDebt × 0.05)* | *Approximation on yfinance path |
| `gross_margin` | `grossProfitMargin` × 100 | `grossMargins` × 100 | % |
| `free_cashflow` | not available on FMP free | `freeCashflow` | Absolute value ($) |
| `market_cap` | `mktCap` | `marketCap` | |
| `sector` / `industry` | `profile` | `.info` | |

**FCF Yield** (qualitative signal — compute when `_source == "yahoo"` or when market_cap is available):
```
FCF Yield = free_cashflow / market_cap × 100
```
FCF Yield > 5% is considered attractive (Brealey-Myers: FCF is the purest measure of value creation).

**What is NOT available** on FMP free + yfinance:
- Forward P/E, PEG ratio (PEG available on yfinance `.info['pegRatio']` — use for combined reports)
- Earnings surprise history / analyst estimates (FMP Starter+ required)
- Revenue YoY growth % (derive from income statement if needed)
- DCF model (FMP Premium; not in the backend — build from OHLCV + FCF manually if needed)
- Sector average comparisons (not available on free tier)
- Short interest (available via yfinance `.info['sharesShort']` / `.info['shortPercentOfFloat']` — not wired into backend yet)
- Institutional ownership breakdown (yfinance provides top-10 holders only)

---

### Screener

**App screener** — Buffett/Brealey 6-criteria value screen:
```
GET /api/screener/run?tickers=AAPL,MSFT,NVDA&min_criteria=4&enrich=true
```

Fixed criteria thresholds:
| Criterion | Threshold | Insight source |
|---|---|---|
| D/E (low leverage) | ≤ 0.5 | Brealey-Myers: financial distress risk |
| Current ratio (liquidity) | ≥ 1.5 | Brealey-Myers Ch.30 |
| P/B (fair valuation) | ≤ 2.0 | Buffett margin-of-safety heuristic |
| ROE (equity returns) | ≥ 10% | Munger: durable competitive advantage |
| ROA (asset productivity) | ≥ 5% | Brealey-Myers DuPont decomposition |
| Interest coverage (debt service) | ≥ 4× | Brealey-Myers Ch.18 |

Stocks scoring ≥ `min_criteria` pass. Set `enrich=true` to attach relevant investment
theses from the knowledge base to each passing stock.

**Standalone universe scanner** — for S&P 500 / Russell 1000 / all-US bulk scans:
```bash
python screener_scripts/market_scanner_full.py
```
Uses yfinance (10 parallel workers, ArcticDB 7-day cache), sector-aware criteria,
and exports a ranked CSV. Do not run this via the API — it can take 5–30 minutes and
will exhaust yfinance rate limits if not cached.

**Thesis enrichment** — for any passing stock, call:
```python
search_theses(entity="NVDA", theme="AI Infrastructure")
```

---

### Combined report (default for "analyze [TICKER]")

Run in this order:
1. `get_quote(symbol)` — live price + day range + volume
2. `GET /api/market/profile/{symbol}` — sector, industry, description
3. `GET /api/screener/run?tickers={symbol}&min_criteria=1&enrich=false` — all fundamentals
4. `GET /api/market/history/{symbol}?from_date=<252d ago>&to_date=<today>` — OHLCV for indicators
5. Compute RSI14, SMA50, SMA200, MACD, Bollinger Bands from OHLCV (see recipes above)
6. `search_theses(entity=symbol, theme=None)` — internal research opinions
7. `get_entity_graph(symbol)` — supply chain / competitor context
8. `search_principles("valuation frameworks risk return")` — cite relevant theory
9. `get_screener_history(5)` — check if this ticker has appeared in past screens

Then produce the report using the template in Step 4.

---

## Step 3 — Error handling

**FMP free tier limits (~250 req/day):**
- On `402 Payment Required` or `403 Forbidden`: yfinance fallback is automatic in the
  backend — the `_source` field in the response will be `"yahoo"` instead of `"fmp"`.
- On `429 Too Many Requests`: the daily quota is exhausted. Inform the user and suggest
  retrying tomorrow or upgrading to FMP Starter ($22/mo) for 300 req/min.
- On `404 Not Found`: verify the ticker is a US-listed equity. FMP free tier does not
  cover international tickers, options, or most ETFs.

**yfinance fragility:**
- `.info`, `.financials`, `.balance_sheet`, `.cashflow` scrape HTML and can return empty
  DataFrames intermittently. If `free_cashflow` or `interest_coverage` is null and the
  source is `"yahoo"`, note this to the user and retry once.
- yfinance `.info` calls take 1–3s per ticker; avoid parallel calls to more than 6 tickers
  simultaneously (the screener already enforces a concurrency semaphore of 6).

**Screener bulk runs:**
- The app screener takes only user-supplied tickers (not a full index). If a user asks
  to screen "all S&P 500 stocks", direct them to `screener_scripts/market_scanner_full.py`
  rather than passing 500 tickers to the API endpoint.

**Symbol format:**
- Use plain US tickers: `AAPL`, `MSFT`, `NVDA`. No exchange suffixes (not `AAPL.US`).
- For crypto: yfinance uses `BTC-USD`; FMP uses `BTCUSD`. Crypto fundamentals are not
  available — technical analysis only.

---

## Coverage caveats — what this stack cannot do

| Capability | Status | Notes |
|---|---|---|
| Intraday bars (1m/5m/15m/1h) | **Not available** on FMP free | Need FMP Premium ($59/mo) for server-side intraday; yfinance 1m is last 5 days only, 5m/15m/1h last 60 days |
| Real-time WebSocket streaming | **Not available** | REST polling only; quote cache refreshes every 30s |
| Server-side technical indicators | **Not available** on free tier | Computed from EOD OHLCV using pandas (see Step 2 recipes) |
| Historical intraday backtesting | **Severely limited** | `backend/routers/simulation.py` operates on EOD OHLCV only |
| Earnings surprise / analyst estimates | **Not available** on FMP free | FMP Starter+ required for `/v3/analyst-estimates` |
| Options data (Greeks, chain) | **Not available** | Out of scope per `change_specs/product_note.md` |
| Macro data (GDP, CPI, yields) | **Not available** in the app | `comprehensive_analysis_enhanced.py` (standalone) uses yfinance for `^TNX`, `^VIX`, `DX-Y.NYB`, `^GSPC` |
| DCF model | **Not built** | FMP Premium has a `/v4/discounted-cash-flow` endpoint; not wired into the backend |
| International tickers | **Limited** | FMP free is US-only; yfinance fallback covers global but with lower reliability |
| Short interest / float | **Not wired** | Available via yfinance `.info['shortPercentOfFloat']` — mention as supplementary data when relevant |

---

## Step 4 — Output templates

### Technical Analysis Output
```
## Technical Analysis — [TICKER] ([DATE])

**Price:** $X.XX | **Change:** +X.XX% | **Volume:** X.XM
**52-week range:** $X.XX — $X.XX (from EOD history, 252 days)

### Trend
- SMA50: $X.XX | SMA200: $X.XX
- Position: [Above / Below] long-term trend (SMA200)
- Trend: [Uptrend / Downtrend / Consolidation]

### Momentum
- RSI (14): XX — [Overbought >70 / Neutral / Oversold <30]
- MACD: [Bullish — histogram positive and widening / Bearish / Neutral]

### Volatility
- Bollinger Bands (20, 2σ): Upper $X.XX | Mid $X.XX | Lower $X.XX
- Price position: [Near upper band (extended) / Near lower band (potential reversal) / Mid-band]

### Data source
- OHLCV: [FMP / yfinance fallback] | Indicators: computed from EOD data (no intraday)
```

### Fundamental Analysis Output
```
## Fundamental Analysis — [TICKER]

**Sector:** X | **Industry:** X | **Market Cap:** $XB
**Data source:** [FMP / yfinance fallback]

### Valuation
| Metric     | Value  | Signal                        |
|------------|--------|-------------------------------|
| P/E        | XX.X   | [Cheap <15 / Fair / Rich >30] |
| P/B        | X.X    | Screener threshold ≤ 2.0      |
| FCF Yield  | X.X%   | [Attractive >5% / Fair / Low] |

### Quality
| Metric           | Value | Screener pass? |
|------------------|-------|----------------|
| ROE              | X.X%  | ≥ 10%          |
| ROA              | X.X%  | ≥ 5%           |
| D/E              | X.X   | ≤ 0.5          |
| Current ratio    | X.X   | ≥ 1.5          |
| Interest coverage| X.X×  | ≥ 4×           |
| Gross margin     | X.X%  | (informational) |

**Screener result:** X/6 criteria passed — [Passes ✓ / Does not pass ✗]

### Research opinions
[From search_theses — label as opinion, include source and date]

### Principles anchor
[From search_principles — cite book title and concept]

### Summary
[2–3 sentence qualitative assessment grounded in the data above]

⚠️ Sector average comparisons not available on FMP free / yfinance.
   Earnings surprise history requires FMP Starter+.
```

### Combined Report (full "analyze [TICKER]")
Run all steps from Step 2 "Combined report" section, then merge Technical + Fundamental
templates above. Add:
```
### Supply chain / competitors
[From get_entity_graph — list key customers, suppliers, competitors]

### Past screener appearances
[From get_screener_history — note dates and criteria scores if the ticker appeared]
```
