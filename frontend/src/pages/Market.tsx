import { useState, useRef, useEffect } from "react";
import { getQuote, getHistory, searchSymbol } from "../api/client";
import { searchTickers } from "../data/tickers";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

interface Suggestion {
  symbol: string;
  name: string;
  exchangeShortName: string;
}

interface Quote {
  symbol: string;
  name: string;
  price: number;
  changesPercentage: number;
  open: number;
  dayHigh: number;
  dayLow: number;
  volume: number;
  marketCap: number;
}

interface HistoryCandle {
  date: string;
  close: number;
}

export default function Market() {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebounce(query, 300);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [history, setHistory] = useState<HistoryCandle[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const wrapperRef = useRef<HTMLDivElement>(null);

  // Show static suggestions instantly on every keystroke (no API call)
  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) { setSuggestions([]); return; }
    const staticResults: Suggestion[] = searchTickers(q).map((t) => ({
      symbol: t.symbol,
      name: t.name,
      exchangeShortName: t.exchange,
    }));
    setSuggestions(staticResults);
  }, [query]);

  // Fire API call only after user pauses typing (300ms debounce) — reduces FMP rate limit usage
  useEffect(() => {
    const q = debouncedQuery.trim();
    if (q.length < 2) return;
    let cancelled = false;
    searchSymbol(q).then((results: Suggestion[]) => {
      if (!cancelled && results.length > 0) setSuggestions(results.slice(0, 8));
    });
    return () => { cancelled = true; };
  }, [debouncedQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setSuggestions([]);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const loadSymbol = async (symbol: string) => {
    setSuggestions([]);
    setQuery(symbol);
    setLoading(true);
    setError("");
    setQuote(null);
    setHistory([]);
    try {
      const [q, h] = await Promise.all([
        getQuote(symbol),
        getHistory(
          symbol,
          new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10),
          new Date().toISOString().slice(0, 10)
        ),
      ]);
      if (!q || !q.price) {
        setError(`No data found for "${symbol}".`);
      } else {
        setQuote(q);
        setHistory(h.map((c: any) => ({ date: c.date, close: c.close })));
      }
    } catch (err: any) {
      const detail = err.response?.data?.detail ?? err.message;
      if (err.response?.status === 403) {
        setError(`FMP API key issue — ${detail}`);
      } else {
        setError(`Failed to fetch data for "${symbol}". Try again.`);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const symbol = query.trim().toUpperCase();
    if (symbol) loadSymbol(symbol);
  };

  const pctColor = quote && quote.changesPercentage >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Market</h1>

      <div ref={wrapperRef} className="relative max-w-sm mb-6">
        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            className="border rounded px-3 py-2 text-sm flex-1"
            placeholder="Search company or ticker e.g. Apple, NVDA"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoComplete="off"
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "…" : "Go"}
          </button>
        </form>

        {suggestions.length > 0 && (
          <ul className="absolute z-10 w-full bg-white rounded-xl shadow-lg border mt-1 divide-y text-sm max-h-64 overflow-y-auto">
            {suggestions.map((r) => (
              <li
                key={r.symbol}
                className="px-4 py-2 hover:bg-blue-50 cursor-pointer flex justify-between items-center gap-2"
                onMouseDown={() => loadSymbol(r.symbol)}
              >
                <span className="font-semibold text-blue-700 shrink-0">{r.symbol}</span>
                <span className="text-gray-500 truncate text-right">{r.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

      {quote && (
        <div className="bg-white rounded-xl shadow p-5 mb-6 max-w-lg">
          <div className="flex items-baseline gap-3">
            <span className="text-xl font-bold">{quote.symbol}</span>
            <span className="text-gray-500 text-sm">{quote.name}</span>
          </div>
          <div className="flex items-baseline gap-3 mt-1">
            <span className="text-3xl font-bold">${quote.price?.toFixed(2)}</span>
            <span className={`font-medium ${pctColor}`}>
              {quote.changesPercentage >= 0 ? "+" : ""}{quote.changesPercentage?.toFixed(2)}%
            </span>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-1 mt-3 text-sm text-gray-600">
            <span>Open: ${quote.open?.toFixed(2)}</span>
            <span>High: ${quote.dayHigh?.toFixed(2)}</span>
            <span>Low: ${quote.dayLow?.toFixed(2)}</span>
            <span>Volume: {quote.volume?.toLocaleString()}</span>
          </div>
        </div>
      )}

      {history.length > 0 && (
        <div className="bg-white rounded-xl shadow p-5">
          <h2 className="text-sm font-medium text-gray-500 mb-3">90-day Price Chart</h2>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v}`} />
              <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, "Close"]} />
              <Line type="monotone" dataKey="close" stroke="#2563eb" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {quote && history.length === 0 && !loading && (
        <p className="text-xs text-gray-400 mt-2">
          Historical chart not available for this symbol on the FMP free tier.
        </p>
      )}
    </div>
  );
}
