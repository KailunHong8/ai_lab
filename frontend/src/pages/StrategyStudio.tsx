import { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import {
  parseToDefinition,
  createStrategy,
  listStrategies,
  getStrategy,
  updateStrategyVersion,
  promoteStrategyVersion,
  compileStrategyVersion,
  validateStrategyVersion,
  runStrategyBacktest,
  listOllamaModels,
  type StrategyDefinition,
  type ValidationFinding,
} from "../api/client";
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
  ComposedChart,
} from "recharts";

// ── Constants ──────────────────────────────────────────────────────────────────

const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];
const OLLAMA_CLOUD_MODELS = ["gpt-oss:120b", "gemma4:31b"];
const OLLAMA_LOCAL_MODELS = ["qwen3.5:9b"];

type StudioTab = "draft" | "rules" | "validation" | "versions" | "report";

// ── Helpers ────────────────────────────────────────────────────────────────────

const fmt = (n: number | undefined | null, decimals = 2, suffix = "") =>
  n == null ? "—" : `${n.toFixed(decimals)}${suffix}`;

const fmtPct = (n: number | undefined | null) => fmt(n, 2, "%");

function SeverityBadge({ sev }: { sev: string }) {
  const cls =
    sev === "error"
      ? "bg-red-100 text-red-700"
      : sev === "warning"
      ? "bg-yellow-100 text-yellow-700"
      : "bg-blue-100 text-blue-600";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase ${cls}`}>
      {sev}
    </span>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border rounded p-3 text-center">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className="text-lg font-bold text-gray-800">{value}</div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function StrategyStudio() {
  const location = useLocation();
  const routerState = location.state as {
    strategy?: string;
    start_date?: string;
    end_date?: string;
  } | null;

  // LLM provider
  const [provider, setProvider] = useState<"bedrock" | "ollama" | "ollama-cloud">("bedrock");
  const [model, setModel] = useState(BEDROCK_MODELS[0]);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);

  // Draft form
  const [description, setDescription] = useState(routerState?.strategy ?? "");
  const [startDate, setStartDate] = useState(routerState?.start_date ?? "2020-01-01");
  const [endDate, setEndDate] = useState(routerState?.end_date ?? "2024-01-01");
  const [strategyName, setStrategyName] = useState("");
  const [benchmark, setBenchmark] = useState("SPY");

  // Studio state
  const [activeTab, setActiveTab] = useState<StudioTab>("draft");
  const [definition, setDefinition] = useState<StrategyDefinition | null>(null);
  const [findings, setFindings] = useState<ValidationFinding[]>([]);
  const [isRunnable, setIsRunnable] = useState(false);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [parserOutput, setParserOutput] = useState<string>("");

  // Persisted IDs
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [versionStatus, setVersionStatus] = useState<string>("draft");

  // Strategy list
  const [strategyList, setStrategyList] = useState<any[]>([]);

  // Validation
  const [validationResult, setValidationResult] = useState<any>(null);

  // Backtest
  const [backtestResult, setBacktestResult] = useState<any>(null);
  const [initialCapital, setInitialCapital] = useState("10000");
  const [monteCarlo, setMonteCarlo] = useState(true);

  // UX
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  useEffect(() => {
    listOllamaModels()
      .then((d: any) => setOllamaAvailable(d.available))
      .catch(() => {});
    refreshStrategyList();
  }, []);

  const handleProviderChange = (p: "bedrock" | "ollama" | "ollama-cloud") => {
    setProvider(p);
    if (p === "bedrock") setModel(BEDROCK_MODELS[0]);
    else if (p === "ollama-cloud") setModel(OLLAMA_CLOUD_MODELS[0]);
    else setModel(OLLAMA_LOCAL_MODELS[0]);
  };

  const modelOptions =
    provider === "bedrock" ? BEDROCK_MODELS :
    provider === "ollama-cloud" ? OLLAMA_CLOUD_MODELS :
    OLLAMA_LOCAL_MODELS;

  async function refreshStrategyList() {
    try {
      const data = await listStrategies();
      setStrategyList(data);
    } catch {}
  }

  // ── Parse ──────────────────────────────────────────────────────────────────

  async function handleParse() {
    if (!description.trim()) { setError("Enter a strategy description first."); return; }
    setError(""); setInfo(""); setLoading(true);
    try {
      const result = await parseToDefinition({
        strategy_description: description,
        start_date: startDate,
        end_date: endDate,
        benchmark,
        provider: provider === "ollama-cloud" ? "ollama-cloud" : provider,
        model,
      });
      setDefinition(result.definition);
      setFindings(result.findings ?? []);
      setIsRunnable(result.is_runnable);
      setParseWarnings(result.parse_warnings ?? []);
      setParserOutput(result.parser_output ?? "");
      setInfo("Strategy parsed. Review the definition below, then save it.");
      setActiveTab("rules");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Save as strategy ───────────────────────────────────────────────────────

  async function handleSave() {
    if (!definition) { setError("Parse a strategy first."); return; }
    if (!strategyName.trim()) { setError("Enter a strategy name."); return; }
    setError(""); setInfo(""); setLoading(true);
    try {
      const result = await createStrategy({
        name: strategyName,
        description,
        definition,
        source_prompt: description,
        parser_output_json: parserOutput,
      });
      setStrategyId(result.strategy_id);
      setVersionId(result.version_id);
      setVersionStatus("draft");
      setFindings(result.findings ?? []);
      setIsRunnable(result.is_runnable);
      setInfo(`Strategy saved. ID: ${result.strategy_id} (version 1, draft)`);
      await refreshStrategyList();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Compile ────────────────────────────────────────────────────────────────

  async function handleCompile() {
    if (!strategyId || !versionId) { setError("Save the strategy first."); return; }
    setError(""); setLoading(true);
    try {
      const result = await compileStrategyVersion(strategyId, versionId);
      setFindings(result.findings ?? []);
      setIsRunnable(result.is_runnable);
      setInfo(result.is_runnable ? "No blocking errors — strategy is runnable." : "Blocking errors found. See findings below.");
      setActiveTab("rules");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Update definition ──────────────────────────────────────────────────────

  async function handleUpdateDefinition() {
    if (!strategyId || !versionId || !definition) return;
    if (versionStatus !== "draft") { setError("Version is no longer a draft."); return; }
    setError(""); setLoading(true);
    try {
      const result = await updateStrategyVersion(strategyId, versionId, definition);
      setFindings(result.findings ?? []);
      setIsRunnable(result.is_runnable);
      setInfo("Definition updated.");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Promote ────────────────────────────────────────────────────────────────

  async function handlePromote() {
    if (!strategyId || !versionId) return;
    if (!isRunnable) { setError("Cannot promote: blocking errors exist."); return; }
    setError(""); setLoading(true);
    try {
      const result = await promoteStrategyVersion(strategyId, versionId);
      setVersionStatus("reviewed");
      setInfo("Version promoted to 'reviewed'. It is now immutable.");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Validate ───────────────────────────────────────────────────────────────

  async function handleValidate() {
    if (!strategyId || !versionId) { setError("Save the strategy first."); return; }
    if (!isRunnable) { setError("Fix blocking errors before validating."); return; }
    setError(""); setInfo("Running validation (this may take a moment)…"); setLoading(true);
    try {
      const result = await validateStrategyVersion(strategyId, versionId, { n_folds: 5, holdout_pct: 0.20, bootstrap_sims: 300 });
      setValidationResult(result);
      setInfo("");
      setActiveTab("validation");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
      setInfo("");
    } finally {
      setLoading(false);
    }
  }

  // ── Backtest ───────────────────────────────────────────────────────────────

  async function handleBacktest() {
    if (!strategyId || !versionId) { setError("Save the strategy first."); return; }
    if (!isRunnable) { setError("Fix blocking errors before running a backtest."); return; }
    setError(""); setInfo("Running backtest…"); setLoading(true);
    try {
      const result = await runStrategyBacktest(strategyId, versionId, {
        initial_capital: parseFloat(initialCapital) || 10000,
        benchmark_symbol: benchmark,
        run_monte_carlo: monteCarlo,
        monte_carlo_sims: 300,
      });
      setBacktestResult(result);
      setInfo("");
      setActiveTab("report");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? String(e));
      setInfo("");
    } finally {
      setLoading(false);
    }
  }

  // ── Load existing strategy ─────────────────────────────────────────────────

  async function handleLoadStrategy(sid: string) {
    setError(""); setLoading(true);
    try {
      const data = await getStrategy(sid);
      setStrategyId(sid);
      setStrategyName(data.name);
      if (data.latest_definition) setDefinition(data.latest_definition);
      const latest = data.versions?.[data.versions.length - 1];
      if (latest) {
        setVersionId(latest.id);
        setVersionStatus(latest.status);
      }
      // Re-compile to get findings
      if (latest) {
        const compiled = await compileStrategyVersion(sid, latest.id);
        setFindings(compiled.findings ?? []);
        setIsRunnable(compiled.is_runnable);
      }
      setStrategyList(await listStrategies());
      setActiveTab("rules");
    } catch (e: any) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  const tabBtn = (tab: StudioTab, label: string) => (
    <button
      onClick={() => setActiveTab(tab)}
      className={`px-4 py-2 text-sm font-medium rounded-t border-b-2 ${
        activeTab === tab
          ? "border-blue-600 text-blue-700 bg-white"
          : "border-transparent text-gray-500 hover:text-gray-700"
      }`}
    >
      {label}
    </button>
  );

  const blockingErrors = findings.filter((f) => f.severity === "error");
  const warnings = findings.filter((f) => f.severity === "warning");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Strategy Studio</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Turn a natural-language strategy into a versioned, validated, inspectable daily-bar backtest.
          </p>
        </div>
        {strategyId && (
          <div className="text-xs text-gray-400 text-right">
            <div>Strategy: <span className="font-mono">{strategyId.slice(0, 8)}…</span></div>
            {versionId && <div>Version: <span className="font-mono">{versionId.slice(0, 8)}…</span> <span className={`ml-1 px-1.5 py-0.5 rounded text-xs font-semibold ${versionStatus === "reviewed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>{versionStatus}</span></div>}
          </div>
        )}
      </div>

      {error && <div className="bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">{error}</div>}
      {info && <div className="bg-blue-50 border border-blue-200 rounded p-3 text-blue-700 text-sm">{info}</div>}

      {/* Gate banner */}
      {strategyId && blockingErrors.length > 0 && (
        <div className="bg-red-50 border border-red-300 rounded p-3 text-sm text-red-800">
          <strong>Blocked:</strong> {blockingErrors.length} error(s) must be resolved before running or promoting.
        </div>
      )}

      {/* Tabs */}
      <div className="border-b flex gap-1">
        {tabBtn("draft", "1. Draft")}
        {tabBtn("rules", "2. Rules & Findings")}
        {tabBtn("validation", "3. Validation")}
        {tabBtn("versions", "4. Versions")}
        {tabBtn("report", "5. Report")}
      </div>

      {/* ── Draft tab ──────────────────────────────────────────────────────── */}
      {activeTab === "draft" && (
        <div className="space-y-4">
          {/* LLM provider */}
          <div className="bg-white border rounded p-4 space-y-3">
            <h3 className="font-semibold text-gray-700">LLM Provider</h3>
            <div className="flex gap-2">
              {(["bedrock", "ollama-cloud", "ollama"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  disabled={p === "ollama" && !ollamaAvailable}
                  className={`px-3 py-1.5 text-sm rounded border ${
                    provider === p ? "bg-blue-600 text-white border-blue-600" : "text-gray-700 border-gray-300 hover:border-blue-400"
                  } disabled:opacity-40`}
                >
                  {p === "bedrock" ? "AWS Bedrock" : p === "ollama-cloud" ? "Ollama Cloud" : `Ollama Local${!ollamaAvailable ? " (offline)" : ""}`}
                </button>
              ))}
            </div>
            <select
              className="border rounded px-2 py-1.5 text-sm w-full max-w-xs"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {modelOptions.map((m) => <option key={m}>{m}</option>)}
            </select>
          </div>

          {/* Description */}
          <div className="bg-white border rounded p-4 space-y-3">
            <h3 className="font-semibold text-gray-700">Strategy Description</h3>
            <textarea
              className="w-full border rounded p-2 text-sm font-mono h-32 resize-y"
              placeholder="e.g. Buy AAPL when it drops 3% in a day, sell on 10% gain or 5% stop-loss. Also hold MSFT at 20% and GOOG at 15%."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="flex gap-3 flex-wrap">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Start date</label>
                <input type="date" className="border rounded px-2 py-1 text-sm" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">End date</label>
                <input type="date" className="border rounded px-2 py-1 text-sm" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Benchmark</label>
                <input className="border rounded px-2 py-1 text-sm w-24" value={benchmark} onChange={(e) => setBenchmark(e.target.value.toUpperCase())} />
              </div>
            </div>
            <button
              onClick={handleParse}
              disabled={loading || !description.trim()}
              className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? "Parsing…" : "Parse Strategy"}
            </button>
          </div>

          {/* Save */}
          {definition && (
            <div className="bg-white border rounded p-4 space-y-3">
              <h3 className="font-semibold text-gray-700">Save as Strategy</h3>
              {parseWarnings.length > 0 && (
                <div className="text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-2">
                  <strong>Parse warnings:</strong> {parseWarnings.join("; ")}
                </div>
              )}
              <input
                className="border rounded px-2 py-1.5 text-sm w-full max-w-sm"
                placeholder="Strategy name"
                value={strategyName}
                onChange={(e) => setStrategyName(e.target.value)}
              />
              <div className="flex gap-2 flex-wrap">
                <button
                  onClick={handleSave}
                  disabled={loading || !strategyName.trim()}
                  className="bg-green-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-green-700 disabled:opacity-50"
                >
                  {loading ? "Saving…" : "Save Strategy"}
                </button>
                {strategyId && (
                  <button
                    onClick={handleUpdateDefinition}
                    disabled={loading || versionStatus !== "draft"}
                    className="border border-gray-300 text-gray-700 px-4 py-2 rounded text-sm hover:border-blue-400 disabled:opacity-50"
                  >
                    Update Draft
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Existing strategies */}
          {strategyList.length > 0 && (
            <div className="bg-white border rounded p-4">
              <h3 className="font-semibold text-gray-700 mb-3">Saved Strategies</h3>
              <div className="space-y-2">
                {strategyList.map((s) => (
                  <div key={s.id} className="flex items-center justify-between border rounded px-3 py-2 text-sm">
                    <div>
                      <span className="font-medium">{s.name}</span>
                      <span className="text-gray-400 ml-2 text-xs">v{s.latest_version_number}</span>
                      <span className={`ml-2 text-xs px-1.5 py-0.5 rounded ${s.latest_status === "reviewed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>{s.latest_status}</span>
                    </div>
                    <button
                      onClick={() => handleLoadStrategy(s.id)}
                      className="text-blue-600 hover:text-blue-800 text-xs"
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Rules & Findings tab ────────────────────────────────────────────── */}
      {activeTab === "rules" && (
        <div className="space-y-4">
          {!definition ? (
            <p className="text-gray-500 text-sm">Parse a strategy on the Draft tab first.</p>
          ) : (
            <>
              {/* Findings */}
              <div className="bg-white border rounded p-4">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-semibold text-gray-700">Static Validation Findings</h3>
                  <div className="flex gap-2">
                    {strategyId && versionId && (
                      <button onClick={handleCompile} disabled={loading} className="text-xs border rounded px-2 py-1 hover:border-blue-400 disabled:opacity-50">Re-compile</button>
                    )}
                    {strategyId && versionId && versionStatus === "draft" && isRunnable && (
                      <button onClick={handlePromote} disabled={loading} className="text-xs bg-green-600 text-white rounded px-2 py-1 hover:bg-green-700 disabled:opacity-50">
                        Promote to Reviewed
                      </button>
                    )}
                  </div>
                </div>
                {findings.length === 0 ? (
                  <p className="text-green-600 text-sm">No findings — definition is valid.</p>
                ) : (
                  <div className="space-y-2">
                    {findings.map((f, i) => (
                      <div key={i} className="flex gap-3 items-start text-sm border rounded px-3 py-2">
                        <SeverityBadge sev={f.severity} />
                        <div>
                          <span className="font-mono text-xs text-gray-400 mr-2">{f.code}</span>
                          {f.field && <span className="text-xs text-gray-400 mr-2">[{f.field}]</span>}
                          {f.message}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Universe */}
              <div className="bg-white border rounded p-4">
                <h3 className="font-semibold text-gray-700 mb-2">Universe</h3>
                <div className="flex flex-wrap gap-2">
                  {definition.universe.instruments.map((inst) => (
                    <div key={inst.ticker} className="border rounded px-2 py-1 text-sm">
                      <span className="font-medium">{inst.ticker}</span>
                      {inst.target_weight != null && (
                        <span className="text-gray-500 ml-1">{(inst.target_weight * 100).toFixed(1)}%</span>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-1">Benchmark: {definition.universe.benchmark_symbol ?? "SPY"}</p>
              </div>

              {/* Signals */}
              <div className="bg-white border rounded p-4">
                <h3 className="font-semibold text-gray-700 mb-2">Signals &amp; Rules</h3>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {definition.signals.buy_pct_drop != null && (
                    <div className="border rounded px-2 py-1 bg-green-50">
                      <span className="text-xs text-gray-500">Buy on drop</span>
                      <div className="font-medium">{definition.signals.buy_pct_drop}%</div>
                    </div>
                  )}
                  {definition.signals.sell_pct_gain != null && (
                    <div className="border rounded px-2 py-1 bg-blue-50">
                      <span className="text-xs text-gray-500">Sell on gain</span>
                      <div className="font-medium">{definition.signals.sell_pct_gain}%</div>
                    </div>
                  )}
                  {definition.signals.stop_loss_pct != null && (
                    <div className="border rounded px-2 py-1 bg-red-50">
                      <span className="text-xs text-gray-500">Stop loss</span>
                      <div className="font-medium">{definition.signals.stop_loss_pct}%</div>
                    </div>
                  )}
                  {definition.signals.hold_days != null && (
                    <div className="border rounded px-2 py-1">
                      <span className="text-xs text-gray-500">Max hold (days)</span>
                      <div className="font-medium">{definition.signals.hold_days}</div>
                    </div>
                  )}
                  {definition.preset && (
                    <div className="border rounded px-2 py-1 bg-purple-50">
                      <span className="text-xs text-gray-500">Preset</span>
                      <div className="font-medium">{definition.preset}</div>
                    </div>
                  )}
                </div>
                {definition.unsupported_intents && definition.unsupported_intents.length > 0 && (
                  <div className="mt-2 text-sm text-yellow-700 bg-yellow-50 border border-yellow-200 rounded p-2">
                    <strong>Unsupported intents (non-executable):</strong>
                    <ul className="list-disc ml-4 mt-1 space-y-0.5">
                      {definition.unsupported_intents.map((s, i) => <li key={i}>{s}</li>)}
                    </ul>
                  </div>
                )}
              </div>

              {/* Execution details */}
              <div className="bg-white border rounded p-4">
                <h3 className="font-semibold text-gray-700 mb-2">Execution</h3>
                <div className="grid grid-cols-3 gap-2 text-sm">
                  <div><span className="text-gray-500">Fill</span><div>{definition.execution?.fill_price ?? "next_open"}</div></div>
                  <div><span className="text-gray-500">Order delay</span><div>{definition.execution?.order_delay_bars ?? 1} bar(s)</div></div>
                  <div><span className="text-gray-500">Sizing</span><div>{definition.sizing?.method ?? "equal_weight"}</div></div>
                  <div><span className="text-gray-500">Commission</span><div>{definition.costs?.commission_bps ?? 2} bps</div></div>
                  <div><span className="text-gray-500">Slippage</span><div>{definition.costs?.base_slippage_bps ?? 5} bps</div></div>
                  <div><span className="text-gray-500">Price basis</span><div>{definition.data.price_basis ?? "price_return"}</div></div>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  Signals computed at bar close → fill at next-bar open (no same-bar fill).
                </p>
              </div>

              {/* Backtest controls */}
              {strategyId && versionId && isRunnable && (
                <div className="bg-white border rounded p-4 space-y-3">
                  <h3 className="font-semibold text-gray-700">Run</h3>
                  <div className="flex gap-3 items-end flex-wrap">
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Initial capital</label>
                      <input
                        className="border rounded px-2 py-1 text-sm w-28"
                        value={initialCapital}
                        onChange={(e) => setInitialCapital(e.target.value)}
                      />
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={monteCarlo} onChange={(e) => setMonteCarlo(e.target.checked)} />
                      Block bootstrap MC
                    </label>
                    <button
                      onClick={handleValidate}
                      disabled={loading}
                      className="border border-blue-500 text-blue-600 px-3 py-2 rounded text-sm hover:bg-blue-50 disabled:opacity-50"
                    >
                      {loading ? "…" : "Run Validation"}
                    </button>
                    <button
                      onClick={handleBacktest}
                      disabled={loading}
                      className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
                    >
                      {loading ? "Running…" : "Run Backtest"}
                    </button>
                  </div>
                  {!isRunnable && (
                    <p className="text-red-600 text-sm">Fix blocking errors before running.</p>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Validation tab ──────────────────────────────────────────────────── */}
      {activeTab === "validation" && (
        <div className="space-y-4">
          {!validationResult ? (
            <div className="text-gray-500 text-sm space-y-2">
              <p>No validation results yet.</p>
              {strategyId && versionId && isRunnable && (
                <button onClick={handleValidate} disabled={loading} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                  {loading ? "Running…" : "Run Validation"}
                </button>
              )}
            </div>
          ) : (
            <>
              {validationResult.warnings?.length > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded p-3 text-sm text-yellow-800">
                  <strong>Warnings:</strong> {validationResult.warnings.join("; ")}
                </div>
              )}

              {/* Summary stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard label="Folds" value={String(validationResult.summary?.n_folds ?? 0)} />
                <StatCard label="Mean OOS Sharpe" value={fmt(validationResult.summary?.mean_oos_sharpe)} />
                <StatCard label="Sharpe Degradation" value={fmtPct(validationResult.summary?.sharpe_degradation_pct)} />
                <StatCard label="Overfit Flags" value={String(validationResult.summary?.n_overfit_flags ?? 0)} />
              </div>

              {/* Fold table */}
              {validationResult.folds?.length > 0 && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Rolling Folds (Out-of-Sample)</h3>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b text-gray-500">
                        <th className="text-left py-1">Fold</th>
                        <th className="text-left">Test period</th>
                        <th className="text-right">Train Sharpe</th>
                        <th className="text-right">OOS Sharpe</th>
                        <th className="text-right">OOS Return</th>
                        <th className="text-right">OOS MaxDD</th>
                        <th className="text-center">Overfit?</th>
                      </tr>
                    </thead>
                    <tbody>
                      {validationResult.folds.map((f: any) => (
                        <tr key={f.fold_index} className={`border-b ${f.overfit_flag ? "bg-red-50" : ""}`}>
                          <td className="py-1">{f.fold_index + 1}</td>
                          <td>{f.test_start} → {f.test_end}</td>
                          <td className="text-right">{fmt(f.train_metrics?.sharpe)}</td>
                          <td className="text-right">{fmt(f.test_metrics?.sharpe)}</td>
                          <td className="text-right">{fmtPct(f.test_metrics?.annualized_return_pct)}</td>
                          <td className="text-right">{fmtPct(f.test_metrics?.max_drawdown_pct)}</td>
                          <td className="text-center">{f.overfit_flag ? "⚠" : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Holdout */}
              {validationResult.holdout && Object.keys(validationResult.holdout).length > 0 && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Final Holdout (Untouched)</h3>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard label="Return" value={fmtPct(validationResult.holdout.annualized_return_pct)} />
                    <StatCard label="Sharpe" value={fmt(validationResult.holdout.sharpe)} />
                    <StatCard label="Max DD" value={fmtPct(validationResult.holdout.max_drawdown_pct)} />
                    <StatCard label="Trades" value={String(validationResult.holdout.trade_count ?? "—")} />
                  </div>
                </div>
              )}

              {/* Bootstrap MC fan */}
              {validationResult.bootstrap?.percentiles && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-1">Block Bootstrap MC (non-holdout)</h3>
                  <p className="text-xs text-gray-400 mb-3">
                    {validationResult.bootstrap.n_sims} paths, block size {validationResult.bootstrap.block_size}, seed {validationResult.bootstrap.seed}.
                    Distribution of modeled paths — not a forecast.
                  </p>
                  <ResponsiveContainer width="100%" height={240}>
                    <ComposedChart data={(() => {
                      const p = validationResult.bootstrap.percentiles;
                      const n = (p["50"] ?? []).length;
                      return Array.from({ length: n }, (_, i) => ({
                        i,
                        p5: p["5"]?.[i],
                        p25: p["25"]?.[i],
                        p50: p["50"]?.[i],
                        p75: p["75"]?.[i],
                        p95: p["95"]?.[i],
                      }));
                    })()}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="i" hide />
                      <YAxis tickFormatter={(v) => `$${Math.round(v)}`} />
                      <Tooltip formatter={(v: any) => `$${Number(v).toFixed(0)}`} />
                      <Area dataKey="p95" fill="#dbeafe" stroke="none" name="p95" />
                      <Area dataKey="p75" fill="#93c5fd" stroke="none" name="p75" />
                      <Line dataKey="p50" stroke="#1d4ed8" dot={false} strokeWidth={2} name="Median" />
                      <Area dataKey="p25" fill="#93c5fd" stroke="none" name="p25" />
                      <Area dataKey="p5" fill="#dbeafe" stroke="none" name="p5" />
                    </ComposedChart>
                  </ResponsiveContainer>
                  <div className="grid grid-cols-3 gap-2 mt-3">
                    <StatCard label="Terminal p5" value={`$${Math.round(validationResult.bootstrap.terminal_p5 ?? 0)}`} />
                    <StatCard label="Terminal p50" value={`$${Math.round(validationResult.bootstrap.terminal_p50 ?? 0)}`} />
                    <StatCard label="Terminal p95" value={`$${Math.round(validationResult.bootstrap.terminal_p95 ?? 0)}`} />
                  </div>
                </div>
              )}

              {/* Regime breakdown */}
              {validationResult.regime_breakdown && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Regime Breakdown (Holdout)</h3>
                  <table className="w-full text-xs">
                    <thead><tr className="border-b text-gray-500"><th className="text-left py-1">Regime</th><th className="text-right">Bars</th><th className="text-right">Mean daily ret</th><th className="text-right">Ann vol</th></tr></thead>
                    <tbody>
                      {Object.entries(validationResult.regime_breakdown).map(([regime, m]: [string, any]) => (
                        <tr key={regime} className="border-b">
                          <td className="py-1 font-medium capitalize">{regime}</td>
                          <td className="text-right">{m.n_bars}</td>
                          <td className="text-right">{fmt(m.mean_daily_return_pct, 4)}%</td>
                          <td className="text-right">{fmt(m.volatility_ann_pct)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Versions tab ────────────────────────────────────────────────────── */}
      {activeTab === "versions" && (
        <div className="space-y-3">
          {!strategyId ? (
            <p className="text-gray-500 text-sm">Save a strategy to see versions.</p>
          ) : (
            <>
              <div className="bg-white border rounded p-4">
                <p className="text-sm text-gray-600">
                  Strategy ID: <span className="font-mono">{strategyId}</span>
                </p>
                {versionId && (
                  <div className="mt-2 text-sm">
                    <div>Current version: <span className="font-mono">{versionId.slice(0, 8)}…</span></div>
                    <div>Status: <span className={`px-2 py-0.5 rounded text-xs font-semibold ${versionStatus === "reviewed" ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>{versionStatus}</span></div>
                    {versionStatus === "draft" && isRunnable && (
                      <button onClick={handlePromote} disabled={loading} className="mt-2 bg-green-600 text-white px-3 py-1.5 rounded text-sm hover:bg-green-700 disabled:opacity-50">
                        Promote to Reviewed
                      </button>
                    )}
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-400 bg-white border rounded p-4">
                <p className="font-semibold text-gray-600 mb-1">Immutability rules</p>
                <ul className="list-disc ml-4 space-y-1">
                  <li>Draft versions can be edited via "Update Draft".</li>
                  <li>Promoted (reviewed) versions are immutable.</li>
                  <li>To make changes after promotion, return to the Draft tab, edit, and save a new strategy version.</li>
                </ul>
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Report tab ──────────────────────────────────────────────────────── */}
      {activeTab === "report" && (
        <div className="space-y-4">
          {!backtestResult ? (
            <div className="text-gray-500 text-sm space-y-2">
              <p>No backtest results yet.</p>
              {strategyId && versionId && isRunnable && (
                <button onClick={handleBacktest} disabled={loading} className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50">
                  {loading ? "Running…" : "Run Backtest"}
                </button>
              )}
            </div>
          ) : (
            <>
              {/* Summary stats */}
              {(() => {
                const s = backtestResult.summary ?? {};
                return (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <StatCard label="Total Return" value={fmtPct(s.total_return_pct)} />
                    <StatCard label="Ann. Return" value={fmtPct(s.annualized_return_pct)} />
                    <StatCard label="Sharpe" value={fmt(s.sharpe)} />
                    <StatCard label="Sortino" value={fmt(s.sortino)} />
                    <StatCard label="Max Drawdown" value={fmtPct(s.max_drawdown_pct)} />
                    <StatCard label="Calmar" value={fmt(s.calmar)} />
                    <StatCard label="Ann. Volatility" value={fmtPct(s.annualized_volatility_pct)} />
                    <StatCard label="Trades" value={String(backtestResult.trade_count ?? s.trade_count ?? 0)} />
                    {s.beta != null && <StatCard label="Beta" value={fmt(s.beta)} />}
                    {s.annualized_alpha_pct != null && <StatCard label="Alpha (ann.)" value={fmtPct(s.annualized_alpha_pct)} />}
                    {s.win_rate_pct != null && <StatCard label="Win Rate" value={fmtPct(s.win_rate_pct)} />}
                    {s.turnover_annualized != null && <StatCard label="Ann. Turnover" value={fmt(s.turnover_annualized, 2, "×")} />}
                  </div>
                );
              })()}

              {/* Simulation run ID */}
              <p className="text-xs text-gray-400">
                Run ID: <span className="font-mono">{backtestResult.simulation_run_id}</span>
                {" · "}Data snapshot: <span className="font-mono">{backtestResult.data_snapshot_id?.slice(0, 8)}…</span>
              </p>

              {/* Equity curve */}
              {backtestResult.equity_curve?.length > 0 && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Equity Curve</h3>
                  <ResponsiveContainer width="100%" height={300}>
                    <LineChart data={backtestResult.equity_curve}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(0, 7)} />
                      <YAxis tickFormatter={(v) => `$${Math.round(v).toLocaleString()}`} />
                      <Tooltip formatter={(v: any) => [`$${Number(v).toFixed(0)}`, "Equity"]} />
                      <ReferenceLine y={parseFloat(initialCapital) || 10000} stroke="#9ca3af" strokeDasharray="4 2" />
                      <Line type="monotone" dataKey="value" stroke="#2563eb" dot={false} strokeWidth={2} name="Equity" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Per-ticker breakdown */}
              {backtestResult.per_ticker?.length > 0 && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Per-Ticker Contribution</h3>
                  <table className="w-full text-xs">
                    <thead><tr className="border-b text-gray-500"><th className="text-left py-1">Ticker</th><th className="text-right">Weight</th><th className="text-right">Return</th><th className="text-right">Trades</th></tr></thead>
                    <tbody>
                      {backtestResult.per_ticker.map((t: any) => (
                        <tr key={t.ticker} className="border-b">
                          <td className="py-1 font-medium">{t.ticker}</td>
                          <td className="text-right">{fmtPct(t.weight_pct)}</td>
                          <td className="text-right">{fmtPct(t.return_pct)}</td>
                          <td className="text-right">{t.trade_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Block bootstrap MC */}
              {backtestResult.monte_carlo?.percentiles && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-1">Block Bootstrap MC</h3>
                  <p className="text-xs text-gray-400 mb-3">
                    {backtestResult.monte_carlo.n_sims} paths. Distribution of modeled paths — not a forecast.
                  </p>
                  <ResponsiveContainer width="100%" height={240}>
                    <ComposedChart data={(() => {
                      const p = backtestResult.monte_carlo.percentiles;
                      const n = (p["50"] ?? []).length;
                      return Array.from({ length: n }, (_, i) => ({
                        i,
                        p5: p["5"]?.[i], p25: p["25"]?.[i], p50: p["50"]?.[i],
                        p75: p["75"]?.[i], p95: p["95"]?.[i],
                      }));
                    })()}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="i" hide />
                      <YAxis tickFormatter={(v) => `$${Math.round(v)}`} />
                      <Tooltip formatter={(v: any) => `$${Number(v).toFixed(0)}`} />
                      <Area dataKey="p95" fill="#dbeafe" stroke="none" />
                      <Area dataKey="p75" fill="#93c5fd" stroke="none" />
                      <Line dataKey="p50" stroke="#1d4ed8" dot={false} strokeWidth={2} name="Median" />
                      <Area dataKey="p25" fill="#93c5fd" stroke="none" />
                      <Area dataKey="p5" fill="#dbeafe" stroke="none" />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Trade log (capped at 50) */}
              {backtestResult.trades?.length > 0 && (
                <div className="bg-white border rounded p-4">
                  <h3 className="font-semibold text-gray-700 mb-2">Trade Log (first 50)</h3>
                  <table className="w-full text-xs">
                    <thead><tr className="border-b text-gray-500"><th className="text-left py-1">Date</th><th>Action</th><th className="text-right">Symbol</th><th className="text-right">Fill</th><th className="text-right">Shares</th><th className="text-right">Commission</th><th className="text-right">P&amp;L</th></tr></thead>
                    <tbody>
                      {backtestResult.trades.slice(0, 50).map((t: any, i: number) => (
                        <tr key={i} className={`border-b ${t.action === "BUY" ? "bg-green-50" : "bg-red-50"}`}>
                          <td className="py-1">{t.date}</td>
                          <td className="font-medium">{t.action}</td>
                          <td className="text-right">{t.symbol}</td>
                          <td className="text-right">${t.fill_price?.toFixed(2)}</td>
                          <td className="text-right">{t.shares?.toFixed(2)}</td>
                          <td className="text-right">${t.commission?.toFixed(2)}</td>
                          <td className="text-right">{t.pnl != null ? `$${t.pnl.toFixed(2)}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {backtestResult.trade_count > 50 && (
                    <p className="text-xs text-gray-400 mt-1">Showing 50 of {backtestResult.trade_count} trades.</p>
                  )}
                </div>
              )}

              {/* Limitations */}
              <div className="bg-gray-50 border rounded p-4 text-xs text-gray-500 space-y-1">
                <p className="font-semibold text-gray-600">Limitations</p>
                <ul className="list-disc ml-4 space-y-1">
                  <li>Daily-bar simulation only. Fills at next-bar open (modeled, not executable).</li>
                  <li>Price return basis — no verified total-return or corporate-action adjustment.</li>
                  <li>Modeled costs (commission + slippage). Actual market impact may differ.</li>
                  <li>Block bootstrap MC is a distribution of modeled paths, not a forward forecast.</li>
                  <li>"Eligible for paper trade" does not imply recommendation quality or expected profit.</li>
                </ul>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
