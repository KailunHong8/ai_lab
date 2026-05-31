import { useState } from "react";
import { runSimulation } from "../api/client";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";

interface SimResult {
  pnl: number;
  pnl_pct: number;
  num_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  equity_curve: { date: string; value: number }[];
  trades: { date: string; action: string; price: number }[];
  parsed_rules: Record<string, unknown>;
}

export default function Simulation() {
  const [form, setForm] = useState({
    strategy_description: "",
    symbol: "AAPL",
    start_date: "2023-01-01",
    end_date: "2024-01-01",
    initial_capital: "10000",
  });
  const [result, setResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await runSimulation({
        ...form,
        initial_capital: parseFloat(form.initial_capital),
      });
      setResult(res);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Strategy Simulation</h1>

      <form onSubmit={handleRun} className="bg-white rounded-xl shadow p-5 mb-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2 flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Strategy Description</label>
          <textarea
            className="border rounded px-3 py-2 text-sm h-20 resize-none"
            placeholder="e.g. Buy when price drops 3% from the previous day's close, sell when up 8% from buy price or after 10 trading days"
            value={form.strategy_description}
            onChange={(e) => setForm({ ...form, strategy_description: e.target.value })}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Symbol</label>
          <input
            className="border rounded px-3 py-2 text-sm"
            value={form.symbol}
            onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Initial Capital ($)</label>
          <input
            type="number"
            min="100"
            step="any"
            className="border rounded px-3 py-2 text-sm"
            value={form.initial_capital}
            onChange={(e) => setForm({ ...form, initial_capital: e.target.value })}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">Start Date</label>
          <input
            type="date"
            className="border rounded px-3 py-2 text-sm"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            required
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-500">End Date</label>
          <input
            type="date"
            className="border rounded px-3 py-2 text-sm"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            required
          />
        </div>
        <div className="sm:col-span-2">
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white rounded px-6 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Running…" : "Run Simulation"}
          </button>
        </div>
      </form>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {result && (
        <div>
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
            {[
              { label: "P&L", value: `${result.pnl >= 0 ? "+" : ""}$${result.pnl.toFixed(2)}`, color: result.pnl >= 0 ? "text-green-600" : "text-red-600" },
              { label: "P&L %", value: `${result.pnl_pct >= 0 ? "+" : ""}${result.pnl_pct.toFixed(2)}%`, color: result.pnl_pct >= 0 ? "text-green-600" : "text-red-600" },
              { label: "# Trades", value: String(result.num_trades), color: "text-gray-900" },
              { label: "Win Rate", value: `${(result.win_rate * 100).toFixed(1)}%`, color: "text-gray-900" },
              { label: "Max Drawdown", value: `${result.max_drawdown_pct.toFixed(2)}%`, color: "text-red-600" },
            ].map((s) => (
              <div key={s.label} className="bg-white rounded-xl shadow p-4">
                <p className="text-xs text-gray-500 uppercase tracking-wide">{s.label}</p>
                <p className={`text-xl font-bold mt-1 ${s.color}`}>{s.value}</p>
              </div>
            ))}
          </div>

          {/* Equity Curve */}
          <div className="bg-white rounded-xl shadow p-5 mb-6">
            <h2 className="text-sm font-medium text-gray-500 mb-3">Equity Curve</h2>
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={result.equity_curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toLocaleString()}`} domain={["auto", "auto"]} />
                <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, "Portfolio"]} />
                <ReferenceLine y={parseFloat(form.initial_capital)} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: "Initial", fontSize: 10 }} />
                <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Parsed Rules */}
          <div className="bg-white rounded-xl shadow p-5">
            <h2 className="text-sm font-medium text-gray-500 mb-2">Parsed Strategy Rules</h2>
            <pre className="text-xs text-gray-700 overflow-x-auto">{JSON.stringify(result.parsed_rules, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
