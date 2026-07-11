# Change Spec - Simulation Strategy Parsing to Holdings + Trading Rules

Date: 2026-06-19
Status: Proposed
Owner: Quant app

---

## 1) Problem Statement

The simulation workflow currently accepts strategy_description, but portfolio holdings are not generated from that description.

This creates friction:

1. Users must manually enter holdings even when the strategy already includes a structured allocation table.
2. Strategy text is parsed for trading rules only, which is insufficient for allocation-driven strategies.
3. Allocation-only strategies cannot run immediately unless users manually copy tickers and weights into portfolio inputs.

---

## 2) Goals

1. Parse strategy_description into both:
   - holdings (ticker + allocation metadata)
   - trading rules (entry/exit/risk rules)
2. Allow users to run portfolio simulation immediately from one strategy description input.
3. Support mixed strategy formats: plain text, bullet list, markdown table, and hybrid text+table.
4. Keep behavior deterministic, transparent, and debuggable with parse warnings.

---

## 3) Non-Goals

1. Autonomous ticker discovery from the open web.
2. Fundamental-quality verification of each ticker in parser phase.
3. Automated portfolio optimization (mean-variance, risk parity, Black-Litterman).
4. Intraday execution logic.

---

## 4) Current State (Code Snapshot)

1. strategy_description is parsed into rule fields (buy_pct_drop, sell_pct_gain, stop_loss_pct, hold_days, etc.).
2. Portfolio simulation endpoint requires holdings input from UI.
3. Simulation page initializes with a static default portfolio and manual editing flow.
4. Agent-to-simulation handoff passes strategy text and single-ticker params, not portfolio holdings.

Result: strategy description is not the source of truth for holdings.

---

## 5) Architecture Decision

Adopt a dual-output strategy parser for simulation:

1. Output A: holdings extraction
2. Output B: trading rules extraction

If holdings are present in strategy_description, they should be used to auto-populate portfolio simulation inputs.

If trading rules are missing but holdings are present, apply a default allocation-run profile so simulation can run immediately.

Default allocation-run profile:

1. buy_pct_drop = 0.0 (enter on first available day)
2. sell_pct_gain = null
3. stop_loss_pct = null
4. hold_days = null
5. behavior equivalent to buy-and-hold through end_date

---

## 6) Parsing Contract (Proposed)

### Input

1. strategy_description: string

### Output

```json
{
  "holdings": [
    {
      "ticker": "AAPL",
      "allocation_pct": 14.0,
      "sector": "Technology",
      "tier": "Core",
      "rationale": "Strong FCF, low D/E, dominant moat, high interest coverage"
    }
  ],
  "trading_rules": {
    "buy_condition": "...",
    "sell_condition": "...",
    "buy_pct_drop": 2.0,
    "sell_pct_gain": 6.0,
    "stop_loss_pct": 4.0,
    "hold_days": 30
  },
  "parse_warnings": [
    "Row 7 had missing tier; defaulted to 'Unknown'"
  ],
  "strategy_mode": "allocation_only | rules_only | allocation_and_rules"
}
```

### Validation and normalization

1. Ticker normalization to uppercase (including dot-class tickers like BRK.B).
2. allocation_pct must be positive.
3. If allocation total != 100, normalize server-side and emit warning.
4. Duplicate tickers are merged by summed allocation_pct and warning emitted.
5. Unknown sectors/tiers are allowed as optional metadata.

---

## 7) API Changes (Proposed)

### New endpoint

1. POST /api/simulation/parse-strategy
   - Input: strategy_description, provider, model
   - Output: parsed holdings + trading rules + warnings + strategy_mode

### Updated endpoint behavior

1. POST /api/simulation/run-portfolio
   - holdings becomes optional when auto_parse_holdings=true
   - if holdings missing, backend parses from strategy_description
   - if rules missing but holdings parsed, backend applies default allocation-run profile
   - response includes parsed_holdings and parse_warnings for transparency
   - existing holdings request shape remains supported for backward compatibility

### Optional request flags

1. auto_parse_holdings: bool (default true)
2. auto_parse_rules: bool (default true)
3. strict_parse: bool (default false; if true, any warning can be promoted to 422)

---

## 8) UI/UX Changes (Proposed)

### Simulation page

1. Add "Auto-fill from strategy" action in Portfolio mode.
2. Show parsed holdings preview table before run.
3. Show parse warnings inline.
4. Keep manual holdings editing available after auto-fill.
5. Show badge when weights are normalized by backend.
6. Require user confirmation (human-in-the-loop review) before executing simulation when holdings were auto-parsed.

### Agent handoff

1. Keep existing "Backtest this strategy" action.
2. If parsed holdings are detected from strategy text, open simulation in Portfolio mode with holdings prefilled.
3. If no holdings are detected, keep Single Ticker mode fallback.

---

## 9) Example Translation (Required Behavior)

Given this strategy table in strategy_description:

| # | Ticker | Sector | Tier | Allocation | Screener Screen Rationale |
|---|---|---|---|---|---|
| 1 | AAPL | Technology | Core | 14% | Strong FCF, low D/E, dominant moat, high interest coverage |
| 2 | MSFT | Technology | Core | 14% | Cloud growth, ROE >30%, low leverage, consistent earnings |
| 3 | JNJ | Healthcare | Core | 12% | Defensive, dividend aristocrat, low beta, solid current ratio |
| 4 | BRK.B | Financials/Diversified | Core | 12% | Buffett's own vehicle - embodies value screen criteria |
| 5 | V | Financials (Payments) | Satellite | 10% | Asset-light, ROE >40%, no inventory risk, P/B high but justified |
| 6 | NVDA | Semiconductors | Satellite | 10% | AI infrastructure leader, strong ROA/ROE - elevated P/B is risk |
| 7 | COST | Consumer Staples | Satellite | 8% | Low D/E, loyal membership moat, consistent ROE, defensive |
| 8 | UNH | Healthcare | Satellite | 8% | Large scale, ROE >20%, critical utility-like revenues |
| 9 | AMZN | Consumer/Cloud | Speculative | 7% | AWS profitability improving, ROA turning positive, high beta |
| 10 | META | Communication | Speculative | 5% | FCF machine, AI investment cycle - elevated risk, high reward |

Expected holdings extraction:

```json
[
  {"ticker":"AAPL","allocation_pct":14.0,"sector":"Technology","tier":"Core"},
  {"ticker":"MSFT","allocation_pct":14.0,"sector":"Technology","tier":"Core"},
  {"ticker":"JNJ","allocation_pct":12.0,"sector":"Healthcare","tier":"Core"},
  {"ticker":"BRK.B","allocation_pct":12.0,"sector":"Financials/Diversified","tier":"Core"},
  {"ticker":"V","allocation_pct":10.0,"sector":"Financials (Payments)","tier":"Satellite"},
  {"ticker":"NVDA","allocation_pct":10.0,"sector":"Semiconductors","tier":"Satellite"},
  {"ticker":"COST","allocation_pct":8.0,"sector":"Consumer Staples","tier":"Satellite"},
  {"ticker":"UNH","allocation_pct":8.0,"sector":"Healthcare","tier":"Satellite"},
  {"ticker":"AMZN","allocation_pct":7.0,"sector":"Consumer/Cloud","tier":"Speculative"},
  {"ticker":"META","allocation_pct":5.0,"sector":"Communication","tier":"Speculative"}
]
```

Expected immediate-run behavior:

1. Holdings auto-populate portfolio simulation input.
2. If no explicit entry/exit rules are present in strategy text, fallback to default allocation-run profile.
3. Simulation executes without requiring manual holdings edits.

---

## 10) Acceptance Criteria

1. A markdown allocation table in strategy_description auto-populates holdings in portfolio simulation.
2. strategy_description parsing returns both holdings and trading rules in one response contract.
3. Portfolio simulation runs when holdings are only present in strategy_description (no manual holdings payload required).
4. When rules are absent but holdings are present, simulation still runs via default allocation-run profile.
5. Parse warnings and normalization events are returned and visible in UI.
6. Existing manual holdings workflow remains supported.
7. Users can review and edit parsed holdings before clicking Run Simulation.
8. Existing API request shape for run-portfolio remains valid.

---

## 11) Implementation Plan (One Shot)

1. Add parser contract types for parsed holdings + rules + warnings.
2. Implement table-aware extraction in simulation parser path.
3. Add parse endpoint for preview/debug.
4. Update run-portfolio endpoint to support holdings auto-parse fallback.
5. Add default allocation-run fallback rules when rules are absent.
6. Update Simulation UI to auto-fill and preview parsed holdings.
7. Update Agent handoff logic for portfolio prefill when holdings are detected.
8. Add tests for table parsing, normalization, and fallback run behavior.

---

## 12) Risks and Mitigations

1. LLM parse drift on noisy table formats.
   - Mitigation: AI-generated strategy format from Copilot + mandatory human-in-the-loop review before run.
2. Ambiguous ticker strings in prose.
   - Mitigation: strict ticker validation and warning list.
3. Silent normalization confusion.
   - Mitigation: surface normalization delta in UI and API response.
4. Backward compatibility risk for existing clients.
   - Mitigation: keep holdings payload supported and preserve old request shape.
