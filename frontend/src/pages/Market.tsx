import { useState } from "react";
import { getQuote, getHistory, searchSymbol } from "../api/client";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

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

interface SearchResult {
  symbol: string;
  name: string;
  exchangeShortName: string;
}

export default function Market() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [quote, setQuote] = useState<Quote | null>(null);
  const [history, setHistory] = useState<HistoryCandle[]>([]);
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setLoading(true);
    try {
      const res = await searchSymbol(query);
      setResults(res.slice(0, 8));
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = async (symbol: string) => {
    setLoading(true);
    setResults([]);
    try {
      const [q, h] = await Promise.all([
        getQuote(symbol),
        getHistory(
          symbol,
          new Date(Date.now() - 90 * 86400000).toISOString().slice(0, 10),
          new Date().toISOString().slice(0, 10)
        ),
      ]);
      setQuote(q);
      setHistory(h.map((c: any) => ({ date: c.date, close: c.close })));
    } finally {
      setLoading(false);
    }
  };

  const pctColor = quote && quote.changesPercentage >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Market</h1>

      <form onSubmit={handleSearch} className="flex gap-2 mb-4">
        <input
          className="border rounded px-3 py-2 text-sm flex-1 max-w-xs"
          placeholder="Search symbol or company name…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" className="bg-blue-600 text-white rounded px-4 py-2 text-sm font-medium hover:bg-blue-700">
          Search
        </button>
      </form>

      {results.length > 0 && (
        <ul className="bg-white rounded-xl shadow mb-4 divide-y text-sm max-w-sm">
          {results.map((r) => (
            <li
              key={r.symbol}
              className="px-4 py-2 hover:bg-gray-50 cursor-pointer flex justify-between"
              onClick={() => handleSelect(r.symbol)}
            >
              <span className="font-medium">{r.symbol}</span>
              <span className="text-gray-500 truncate ml-2">{r.name}</span>
            </li>
          ))}
        </ul>
      )}

      {loading && <p className="text-gray-500 text-sm">Loading…</p>}

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
    </div>
  );
}
