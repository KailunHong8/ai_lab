import { useState } from "react";
import { runScreener } from "../api/client";

interface CriteriaDetail {
  low_leverage: boolean;
  good_liquidity: boolean;
  fair_valuation: boolean;
  strong_roe: boolean;
  strong_roa: boolean;
  debt_serviceable: boolean;
}

interface Thesis {
  id: string;
  source: string;
  entity: string | null;
  theme: string | null;
  stance: string;
  claims: string[];
  type: string;
  date: string | null;
}

interface Stock {
  symbol: string;
  name: string;
  sector: string;
  price: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  pb_ratio: number | null;
  roe: number | null;
  roa: number | null;
  debt_equity: number | null;
  current_ratio: number | null;
  gross_margin: number | null;
  criteria_passed: number;
  criteria_detail: CriteriaDetail;
  passes_screen: boolean;
  theses?: Thesis[];
  principles_note?: string;
}

interface Criteria {
  debt_equity_max: number;
  current_ratio_min: number;
  pb_max: number;
  roe_min: number;
  roa_min: number;
  interest_coverage_min: number;
}

const CRITERIA_LABELS: Record<keyof CriteriaDetail, string> = {
  low_leverage: "Low Leverage",
  good_liquidity: "Good Liquidity",
  fair_valuation: "Fair Valuation",
  strong_roe: "Strong ROE",
  strong_roa: "Strong ROA",
  debt_serviceable: "Debt Serviceable",
};

const DEFAULT_TICKERS =
  "AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,BRK-B,JPM,JNJ,PG,KO,V,WMT,XOM";

function fmt(v: number | null | undefined, decimals = 2, suffix = ""): string {
  if (v == null) return "—";
  return v.toFixed(decimals) + suffix;
}

function fmtCap(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v}`;
}

export default function Screener() {
  const [tickers, setTickers] = useState(DEFAULT_TICKERS);
  const [minCriteria, setMinCriteria] = useState(4);
  const [results, setResults] = useState<Stock[]>([]);
  const [criteria, setCriteria] = useState<Criteria | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const handleRun = async () => {
    if (!tickers.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setExpanded(null);
    try {
      const data = await runScreener(tickers, minCriteria);
      setResults(data.results || []);
      setCriteria(data.criteria || null);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setLoading(false);
    }
  };

  const displayed = showAll ? results : results.filter((r) => r.passes_screen || r.criteria_passed >= minCriteria);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Value Screener</h1>
      <p className="text-sm text-gray-500">
        Screens stocks using Buffett/Brealey/Munger criteria, then enriches passing
        stocks with ARK research theses and investing principles.
      </p>

      {/* Controls */}
      <div className="bg-white rounded-xl shadow p-5 space-y-4">
        <div>
          <label className="text-xs text-gray-500 block mb-1">
            Tickers (comma-separated)
          </label>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm h-20 resize-y font-mono"
            value={tickers}
            onChange={(e) => setTickers(e.target.value)}
          />
        </div>

        <div className="flex items-center gap-6 flex-wrap">
          <div>
            <label className="text-xs text-gray-500 block mb-1">
              Min criteria to pass (1–6)
            </label>
            <input
              type="number"
              min={1}
              max={6}
              value={minCriteria}
              onChange={(e) => setMinCriteria(Number(e.target.value))}
              className="border rounded px-3 py-1.5 text-sm w-20"
            />
          </div>

          <button
            onClick={handleRun}
            disabled={loading}
            className="mt-4 bg-blue-600 text-white rounded px-6 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Screening…" : "Run Screen"}
          </button>

          {results.length > 0 && (
            <label className="flex items-center gap-2 text-sm mt-4 cursor-pointer">
              <input
                type="checkbox"
                checked={showAll}
                onChange={(e) => setShowAll(e.target.checked)}
              />
              Show all tickers
            </label>
          )}
        </div>

        {criteria && (
          <div className="text-xs text-gray-400 border-t pt-3">
            Criteria thresholds — D/E ≤ {criteria.debt_equity_max} | Current Ratio ≥{" "}
            {criteria.current_ratio_min} | P/B ≤ {criteria.pb_max} | ROE ≥{" "}
            {criteria.roe_min}% | ROA ≥ {criteria.roa_min}% | Interest Coverage ≥{" "}
            {criteria.interest_coverage_min}
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      {/* Results */}
      {displayed.length > 0 && (
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            {results.filter((r) => r.passes_screen).length} of {results.length} stocks pass ≥{minCriteria} criteria.
            {!showAll && ` Showing ${displayed.length} passing.`}
          </p>

          {displayed.map((stock) => (
            <div
              key={stock.symbol}
              className={`bg-white rounded-xl shadow overflow-hidden border-l-4 ${
                stock.passes_screen ? "border-green-500" : "border-gray-200"
              }`}
            >
              {/* Header row */}
              <div
                className="px-5 py-4 cursor-pointer select-none"
                onClick={() => setExpanded(expanded === stock.symbol ? null : stock.symbol)}
              >
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-base">{stock.symbol}</span>
                    <span className="text-sm text-gray-500 truncate max-w-xs">{stock.name}</span>
                    {stock.sector && (
                      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-500">
                        {stock.sector}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`text-sm font-semibold px-2 py-0.5 rounded ${
                        stock.passes_screen
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      }`}
                    >
                      {stock.criteria_passed}/6
                    </span>
                    <span className="text-gray-400 text-xs">{expanded === stock.symbol ? "▲" : "▼"}</span>
                  </div>
                </div>

                {/* Criteria pills */}
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {(Object.keys(stock.criteria_detail) as (keyof CriteriaDetail)[]).map((k) => (
                    <span
                      key={k}
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        stock.criteria_detail[k]
                          ? "bg-green-100 text-green-700"
                          : "bg-red-50 text-red-400"
                      }`}
                    >
                      {CRITERIA_LABELS[k]}
                    </span>
                  ))}
                </div>
              </div>

              {/* Expanded detail */}
              {expanded === stock.symbol && (
                <div className="border-t px-5 py-4 space-y-5 bg-gray-50">
                  {/* Fundamentals grid */}
                  <div>
                    <h3 className="text-xs font-semibold text-gray-400 uppercase mb-2">
                      Fundamentals
                    </h3>
                    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
                      {[
                        ["Price", fmt(stock.price, 2, "")],
                        ["Market Cap", fmtCap(stock.market_cap)],
                        ["P/E", fmt(stock.pe_ratio, 1)],
                        ["P/B", fmt(stock.pb_ratio, 2)],
                        ["ROE", fmt(stock.roe, 1, "%")],
                        ["ROA", fmt(stock.roa, 1, "%")],
                        ["D/E", fmt(stock.debt_equity, 2)],
                        ["Curr. Ratio", fmt(stock.current_ratio, 2)],
                        ["Gross Margin", fmt(stock.gross_margin, 1, "%")],
                      ].map(([label, value]) => (
                        <div key={label} className="bg-white rounded p-2 text-center shadow-sm">
                          <p className="text-xs text-gray-400">{label}</p>
                          <p className="text-sm font-semibold">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* ARK Theses */}
                  {stock.theses && stock.theses.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase mb-2">
                        Research Theses
                      </h3>
                      <div className="space-y-2">
                        {stock.theses.map((t) => (
                          <div key={t.id} className="bg-white rounded p-3 shadow-sm text-sm">
                            <div className="flex items-center gap-2 mb-1 flex-wrap">
                              <span
                                className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                                  t.stance === "bullish"
                                    ? "bg-green-100 text-green-700"
                                    : t.stance === "bearish"
                                    ? "bg-red-100 text-red-600"
                                    : "bg-gray-100 text-gray-500"
                                }`}
                              >
                                {t.stance}
                              </span>
                              {t.theme && (
                                <span className="text-xs text-gray-500">{t.theme}</span>
                              )}
                              <span className="text-xs text-gray-400 ml-auto">
                                {t.source}{t.date ? ` · ${t.date}` : ""}
                              </span>
                            </div>
                            <ul className="list-disc list-inside text-xs text-gray-600 space-y-0.5">
                              {t.claims.map((c, i) => (
                                <li key={i}>{c}</li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Principles note */}
                  {stock.principles_note && (
                    <div>
                      <h3 className="text-xs font-semibold text-gray-400 uppercase mb-2">
                        Principles Library
                      </h3>
                      <p className="text-xs text-gray-600 bg-white rounded p-3 shadow-sm leading-relaxed">
                        {stock.principles_note}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {!loading && results.length === 0 && !error && (
        <p className="text-sm text-gray-400">Enter tickers above and run the screen.</p>
      )}
    </div>
  );
}
