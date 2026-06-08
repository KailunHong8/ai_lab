import { useEffect, useState } from "react";
import { runSimulation, listOllamaModels } from "../api/client";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
  Legend,
  Area,
  AreaChart,
  ComposedChart,
} from "recharts";

// ── Types ─────────────────────────────────────────────────────────────────────

interface StressPeriod {
  period: string;
  start?: string;
  end?: string;
  pnl_pct?: number;
  num_trades?: number;
  equity_curve?: { date: string; value: number }[];
  error?: string;
}

interface WalkForward {
  in_sample_days: number;
  out_of_sample_days: number;
  in_sample_pnl_pct: number;
  out_of_sample_pnl_pct: number;
  overfit_warning: boolean;
  in_sample_equity: { date: string; value: number }[];
  out_of_sample_equity: { date: string; value: number }[];
  error?: string;
}

interface MonteCarlo {
  n_simulations: number;
  horizon_days: number;
  p5_final: number;
  p25_final: number;
  p50_final: number;
  p75_final: number;
  p95_final: number;
  prob_profit_pct: number;
  fan_curve: { day: number; p5: number; p25: number; p50: number; p75: number; p95: number }[];
  error?: string;
}

interface SimResult {
  pnl: number;
  pnl_pct: number;
  annual_return_pct?: number;
  num_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  avg_drawdown_pct?: number;
  sharpe?: number;
  sortino?: number;
  calmar?: number;
  beta?: number | null;
  alpha_ann_pct?: number | null;
  momentum_flag?: string | null;
  equity_curve: { date: string; value: number }[];
  trades: { date: string; action: string; price: number }[];
  parsed_rules: Record<string, unknown>;
  benchmark?: string;
  monte_carlo?: MonteCarlo;
  walk_forward?: WalkForward;
  stress_tests?: StressPeriod[];
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];

function StatCard({
  label,
  value,
  color,
  hint,
}: {
  label: string;
  value: string;
  color?: string;
  hint?: string;
}) {
  return (
    <div className="bg-white rounded-xl shadow p-4" title={hint}>
      <p className="text-xs text-gray-500 uppercase tracking-wide">{label}</p>
      <p className={`text-xl font-bold mt-1 ${color ?? "text-gray-900"}`}>{value}</p>
    </div>
  );
}

function fmt(v: number | null | undefined, dec = 2, suffix = ""): string {
  if (v == null) return "—";
  return v.toFixed(dec) + suffix;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Simulation() {
  const [form, setForm] = useState({
    strategy_description: "",
    symbol: "AAPL",
    benchmark_symbol: "SPY",
    start_date: "2020-01-01",
    end_date: "2024-01-01",
    initial_capital: "10000",
    monte_carlo_sims: "300",
    run_monte_carlo: true,
    run_walk_forward: true,
    run_stress_tests: true,
  });
  const [provider, setProvider] = useState<"bedrock" | "ollama">("bedrock");
  const [model, setModel] = useState<string>(BEDROCK_MODELS[0]);
  const [ollamaModels, setOllamaModels] = useState<string[]>(["qwen2.5:9b"]);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"equity" | "mc" | "wf" | "stress" | "rules">("equity");

  useEffect(() => {
    listOllamaModels()
      .then((d: { models: string[]; available: boolean }) => {
        setOllamaAvailable(d.available);
        if (d.models.length > 0) setOllamaModels(d.models);
      })
      .catch(() => {});
  }, []);

  const handleProviderChange = (p: "bedrock" | "ollama") => {
    setProvider(p);
    setModel(p === "bedrock" ? BEDROCK_MODELS[0] : ollamaModels[0] || "qwen2.5:9b");
  };

  const handleRun = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await runSimulation({
        strategy_description: form.strategy_description,
        symbol: form.symbol,
        benchmark_symbol: form.benchmark_symbol,
        start_date: form.start_date,
        end_date: form.end_date,
        initial_capital: parseFloat(form.initial_capital),
        monte_carlo_sims: parseInt(form.monte_carlo_sims),
        run_monte_carlo: form.run_monte_carlo,
        run_walk_forward: form.run_walk_forward,
        run_stress_tests: form.run_stress_tests,
        provider,
        model: model || undefined,
      });
      setResult(res);
      setActiveTab("equity");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? err.message);
    } finally {
      setLoading(false);
    }
  };

  const modelOptions = provider === "bedrock" ? BEDROCK_MODELS : ollamaModels;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Strategy Simulation</h1>

      {/* ── Form ── */}
      <form onSubmit={handleRun} className="bg-white rounded-xl shadow p-5 mb-6 space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2 flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500">Strategy Description</label>
            <textarea
              className="border rounded px-3 py-2 text-sm h-20 resize-none"
              placeholder="e.g. Buy when price drops 3% from previous day's close, sell when up 8% or after 10 trading days"
              value={form.strategy_description}
              onChange={(e) => setForm({ ...form, strategy_description: e.target.value })}
              required
            />
          </div>

          {[
            ["Symbol", "symbol"],
            ["Benchmark", "benchmark_symbol"],
            ["Start Date", "start_date", "date"],
            ["End Date", "end_date", "date"],
            ["Initial Capital ($)", "initial_capital", "number"],
            ["Monte Carlo Sims", "monte_carlo_sims", "number"],
          ].map(([label, key, type]) => (
            <div key={key} className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-500">{label}</label>
              <input
                type={type || "text"}
                className="border rounded px-3 py-2 text-sm"
                value={(form as any)[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                required
              />
            </div>
          ))}
        </div>

        {/* Options row */}
        <div className="flex flex-wrap gap-5 text-sm items-center border-t pt-3">
          {[
            ["Monte Carlo", "run_monte_carlo"],
            ["Walk-Forward", "run_walk_forward"],
            ["Stress Tests", "run_stress_tests"],
          ].map(([label, key]) => (
            <label key={key} className="flex items-center gap-1.5 cursor-pointer text-xs text-gray-600">
              <input
                type="checkbox"
                checked={(form as any)[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}

          <span className="text-gray-300">|</span>

          <span className="text-xs text-gray-500">LLM:</span>
          <div className="flex rounded border overflow-hidden">
            {(["bedrock", "ollama"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => handleProviderChange(p)}
                className={`px-3 py-1 text-xs font-medium ${
                  provider === p ? "bg-blue-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
                }`}
              >
                {p === "bedrock" ? "Bedrock" : `Ollama${!ollamaAvailable ? " (offline)" : ""}`}
              </button>
            ))}
          </div>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="border rounded px-2 py-1 text-xs text-gray-700 bg-white"
          >
            {modelOptions.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="bg-blue-600 text-white rounded px-6 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Running…" : "Run Simulation"}
        </button>
      </form>

      {error && <p className="text-red-600 text-sm mb-4">{error}</p>}

      {result && (
        <div>
          {/* ── Stat cards ── */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mb-6">
            <StatCard label="P&L" value={`${result.pnl >= 0 ? "+" : ""}$${result.pnl.toFixed(2)}`} color={result.pnl >= 0 ? "text-green-600" : "text-red-600"} />
            <StatCard label="Ann. Return" value={fmt(result.annual_return_pct, 1, "%")} color={(result.annual_return_pct ?? 0) >= 0 ? "text-green-600" : "text-red-600"} />
            <StatCard label="Sharpe" value={fmt(result.sharpe, 2)} hint="Excess return / total volatility. >1 = good, >2 = excellent." />
            <StatCard label="Sortino" value={fmt(result.sortino, 2)} hint="Like Sharpe but only penalises downside volatility." />
            <StatCard label="Calmar" value={fmt(result.calmar, 2)} hint="Annual return / max drawdown. >1 = efficient risk use." />
            <StatCard label="Max Drawdown" value={`-${fmt(result.max_drawdown_pct, 2, "%")}`} color="text-red-600" />
            <StatCard label="Win Rate" value={`${(result.win_rate * 100).toFixed(1)}%`} />
            <StatCard label="# Trades" value={String(result.num_trades)} />
            {result.beta != null && <StatCard label="Beta" value={fmt(result.beta, 2)} hint={`vs ${result.benchmark}. >1 = more volatile than market.`} />}
            {result.alpha_ann_pct != null && <StatCard label="Alpha (ann.)" value={fmt(result.alpha_ann_pct, 2, "%")} color={(result.alpha_ann_pct ?? 0) >= 0 ? "text-green-600" : "text-red-600"} hint="Return unexplained by market beta." />}
            {result.avg_drawdown_pct != null && <StatCard label="Avg DD" value={`-${fmt(result.avg_drawdown_pct, 2, "%")}`} />}
            {result.momentum_flag && <StatCard label="Momentum" value={result.momentum_flag === "positive" ? "↑ Pos." : "↓ Neg."} color={result.momentum_flag === "positive" ? "text-green-600" : "text-red-600"} hint="60-day trailing return direction." />}
          </div>

          {/* ── Tabs ── */}
          <div className="flex gap-1 mb-4 text-sm flex-wrap">
            {(
              [
                ["equity", "Equity Curve"],
                result.monte_carlo && !result.monte_carlo.error ? ["mc", "Monte Carlo"] : null,
                result.walk_forward && !result.walk_forward.error ? ["wf", "Walk-Forward"] : null,
                result.stress_tests?.length ? ["stress", "Stress Tests"] : null,
                ["rules", "Parsed Rules"],
              ] as ([string, string] | null)[]
            )
              .filter(Boolean)
              .map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key as any)}
                  className={`px-3 py-1.5 rounded text-sm font-medium ${
                    activeTab === key ? "bg-blue-600 text-white" : "bg-white border text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {label}
                </button>
              ))}
          </div>

          {/* ── Equity Curve tab ── */}
          {activeTab === "equity" && (
            <div className="bg-white rounded-xl shadow p-5">
              <h2 className="text-sm font-medium text-gray-500 mb-3">Equity Curve</h2>
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={result.equity_curve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toLocaleString()}`} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, "Portfolio"]} />
                  <ReferenceLine y={parseFloat(form.initial_capital)} stroke="#94a3b8" strokeDasharray="4 4" />
                  <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Monte Carlo tab ── */}
          {activeTab === "mc" && result.monte_carlo && !result.monte_carlo.error && (
            <div className="bg-white rounded-xl shadow p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-medium text-gray-500">
                  Monte Carlo ({result.monte_carlo.n_simulations} paths, {result.monte_carlo.horizon_days} days)
                </h2>
                <span className={`text-sm font-semibold ${result.monte_carlo.prob_profit_pct >= 50 ? "text-green-600" : "text-red-500"}`}>
                  {result.monte_carlo.prob_profit_pct}% probability of profit
                </span>
              </div>

              {/* Percentile summary */}
              <div className="grid grid-cols-5 gap-2 text-center text-xs">
                {[
                  ["P5 (Bear)", result.monte_carlo.p5_final, "text-red-600"],
                  ["P25", result.monte_carlo.p25_final, "text-orange-500"],
                  ["P50 (Median)", result.monte_carlo.p50_final, "text-blue-600"],
                  ["P75", result.monte_carlo.p75_final, "text-green-500"],
                  ["P95 (Bull)", result.monte_carlo.p95_final, "text-green-700"],
                ].map(([label, val, color]) => (
                  <div key={label as string} className="bg-gray-50 rounded p-2">
                    <p className="text-gray-400">{label}</p>
                    <p className={`font-bold text-sm ${color}`}>${Number(val).toLocaleString()}</p>
                  </div>
                ))}
              </div>

              {/* Fan chart */}
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={result.monte_carlo.fan_curve}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="day" tick={{ fontSize: 10 }} label={{ value: "Trading days", fontSize: 10, position: "insideBottom", offset: -2 }} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v, n) => [`$${Number(v).toFixed(0)}`, n]} />
                  <Area type="monotone" dataKey="p95" fill="#bbf7d0" stroke="none" name="P95" />
                  <Area type="monotone" dataKey="p75" fill="#d1fae5" stroke="none" name="P75" />
                  <Area type="monotone" dataKey="p25" fill="#fee2e2" stroke="none" name="P25" fillOpacity={0.5} />
                  <Area type="monotone" dataKey="p5"  fill="#fecaca" stroke="none" name="P5"  fillOpacity={0.5} />
                  <Line type="monotone" dataKey="p50" stroke="#2563eb" dot={false} strokeWidth={2} name="Median" />
                  <ReferenceLine y={parseFloat(form.initial_capital)} stroke="#94a3b8" strokeDasharray="4 4" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Walk-Forward tab ── */}
          {activeTab === "wf" && result.walk_forward && !result.walk_forward.error && (
            <div className="bg-white rounded-xl shadow p-5 space-y-4">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-medium text-gray-500">Walk-Forward Validation (70/30 split)</h2>
                {result.walk_forward.overfit_warning && (
                  <span className="text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full font-medium">
                    Overfit warning
                  </span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-4 text-sm">
                {[
                  ["In-Sample Days", result.walk_forward.in_sample_days, ""],
                  ["Out-of-Sample Days", result.walk_forward.out_of_sample_days, ""],
                  ["In-Sample P&L", `${result.walk_forward.in_sample_pnl_pct >= 0 ? "+" : ""}${result.walk_forward.in_sample_pnl_pct.toFixed(2)}%`, result.walk_forward.in_sample_pnl_pct >= 0 ? "text-green-600" : "text-red-600"],
                  ["Out-of-Sample P&L", `${result.walk_forward.out_of_sample_pnl_pct >= 0 ? "+" : ""}${result.walk_forward.out_of_sample_pnl_pct.toFixed(2)}%`, result.walk_forward.out_of_sample_pnl_pct >= 0 ? "text-green-600" : "text-red-600"],
                ].map(([label, val, color]) => (
                  <div key={label as string} className="bg-gray-50 rounded p-3">
                    <p className="text-xs text-gray-400">{label}</p>
                    <p className={`font-semibold ${color}`}>{val}</p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-400">
                {result.walk_forward.overfit_warning
                  ? "Strategy performs well in-sample but poorly out-of-sample — likely overfitted to the training period. Consider a simpler rule set or wider parameter ranges."
                  : "In-sample and out-of-sample returns are consistent — no strong overfit signal detected."}
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v?.slice(5) ?? ""} />
                  <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${v.toLocaleString()}`} domain={["auto", "auto"]} />
                  <Tooltip formatter={(v, n) => [`$${Number(v).toFixed(2)}`, n]} />
                  <Legend />
                  <Line data={result.walk_forward.in_sample_equity} type="monotone" dataKey="value" stroke="#2563eb" dot={false} strokeWidth={1.5} name="In-sample" />
                  <Line data={result.walk_forward.out_of_sample_equity} type="monotone" dataKey="value" stroke="#f59e0b" dot={false} strokeWidth={1.5} name="Out-of-sample" strokeDasharray="5 3" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* ── Stress Tests tab ── */}
          {activeTab === "stress" && result.stress_tests && (
            <div className="space-y-4">
              {result.stress_tests.map((st) => (
                <div key={st.period} className="bg-white rounded-xl shadow p-5">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-sm font-semibold">{st.period}</h3>
                    {st.error ? (
                      <span className="text-xs text-gray-400">{st.error}</span>
                    ) : (
                      <span className={`text-sm font-bold ${(st.pnl_pct ?? 0) >= 0 ? "text-green-600" : "text-red-600"}`}>
                        {(st.pnl_pct ?? 0) >= 0 ? "+" : ""}{st.pnl_pct?.toFixed(2)}%
                      </span>
                    )}
                  </div>
                  {st.equity_curve && st.equity_curve.length > 0 && (
                    <ResponsiveContainer width="100%" height={160}>
                      <LineChart data={st.equity_curve}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f5f5f5" />
                        <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v.slice(5)} />
                        <YAxis tick={{ fontSize: 9 }} tickFormatter={(v) => `$${v.toLocaleString()}`} domain={["auto", "auto"]} />
                        <Tooltip formatter={(v) => [`$${Number(v).toFixed(2)}`, "Portfolio"]} />
                        <Line type="monotone" dataKey="value" stroke={(st.pnl_pct ?? 0) >= 0 ? "#16a34a" : "#dc2626"} dot={false} strokeWidth={1.5} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* ── Parsed Rules tab ── */}
          {activeTab === "rules" && (
            <div className="bg-white rounded-xl shadow p-5">
              <h2 className="text-sm font-medium text-gray-500 mb-2">Parsed Strategy Rules</h2>
              <pre className="text-xs text-gray-700 overflow-x-auto">
                {JSON.stringify(result.parsed_rules, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
