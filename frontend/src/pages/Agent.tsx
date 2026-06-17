import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  agentChat,
  listSessions,
  createSession,
  getSessionMessages,
  deleteSession,
  renameSession,
  listOllamaModels,
} from "../api/client";

interface Message {
  role: "user" | "assistant";
  text: string;
  intent?: string;   // which specialist answered: research | advice | both
}

type AgentMode = "auto" | "advice" | "research";

const INTENT_LABEL: Record<string, string> = {
  research: "🔎 Deep Research",
  advice: "📊 Investment Advice",
  both: "🔎+📊 Research → Advice",
};

interface Session {
  id: string;
  name: string | null;
  provider: string;
  model: string | null;
  created_at: string;
  updated_at: string;
}

const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];
const OLLAMA_LOCAL_MODELS = ["qwen3.5:9b"];
const OLLAMA_CLOUD_MODELS = ["gpt-oss:120b", "gemma4:31b"];

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

interface BacktestModal {
  text: string;       // assistant message text that contains the strategy
}

export default function Agent() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState<"bedrock" | "ollama" | "ollama-cloud">("bedrock");
  const [model, setModel] = useState<string>(BEDROCK_MODELS[0]);
  const [agentMode, setAgentMode] = useState<AgentMode>("auto");
  const [ollamaAvailable, setOllamaAvailable] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [backtestModal, setBacktestModal] = useState<BacktestModal | null>(null);
  const [btForm, setBtForm] = useState({ symbol: "SPY", start_date: "2020-01-01", end_date: "2024-01-01", initial_capital: "10000" });
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Check Ollama availability + load session list on mount
  useEffect(() => {
    listOllamaModels()
      .then((data: { models: string[]; available: boolean }) => {
        setOllamaAvailable(data.available);
      })
      .catch(() => {});

    refreshSessions();
  }, []);

  const refreshSessions = () =>
    listSessions()
      .then((d: { sessions: Session[] }) => setSessions(d.sessions))
      .catch(() => {});

  const handleProviderChange = (p: "bedrock" | "ollama" | "ollama-cloud") => {
    setProvider(p);
    if (p === "bedrock") setModel(BEDROCK_MODELS[0]);
    else if (p === "ollama-cloud") setModel(OLLAMA_CLOUD_MODELS[0]);
    else setModel(OLLAMA_LOCAL_MODELS[0]);
  };

  // Load a session and its message history
  const loadSession = async (id: string) => {
    setActiveId(id);
    setMessages([]);
    try {
      const data = await getSessionMessages(id);
      const mapped: Message[] = (data.history || []).map((m: { role: string; content: { text?: string }[] }) => ({
        role: m.role as "user" | "assistant",
        text: m.content.map((c) => c.text || "").join(""),
      }));
      setMessages(mapped);
      if (data.provider) setProvider(data.provider);
      if (data.model) setModel(data.model);
    } catch {}
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  const handleNewSession = async () => {
    const data = await createSession(undefined, provider, model);
    await refreshSessions();
    await loadSession(data.id);
    setMessages([]);
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    await deleteSession(id);
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
    }
    await refreshSessions();
  };

  const handleRenameSubmit = async (id: string) => {
    if (renameValue.trim()) await renameSession(id, renameValue.trim());
    setRenamingId(null);
    setRenameValue("");
    await refreshSessions();
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const send = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!input.trim() || loading || !activeId) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setLoading(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const data = await agentChat(userMsg, activeId, provider, model, ctrl.signal, agentMode);
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply, intent: data.intent }]);
      // Update session name if the backend auto-titled it
      if (data.session_name) {
        setSessions((prev) =>
          prev.map((s) => (s.id === activeId ? { ...s, name: data.session_name } : s))
        );
      }
      await refreshSessions();
    } catch (err: any) {
      if (err.name === "CanceledError" || err.code === "ERR_CANCELED") {
        setMessages((prev) => prev.slice(0, -1)); // remove the optimistic user bubble
        setInput(userMsg); // restore input so user can re-type
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Error: ${err.response?.data?.detail ?? err.message}` },
        ]);
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
      setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  const modelOptions =
    provider === "bedrock" ? BEDROCK_MODELS :
    provider === "ollama-cloud" ? OLLAMA_CLOUD_MODELS :
    OLLAMA_LOCAL_MODELS;

  return (
    <div className="flex h-[calc(100vh-96px)] gap-4">
      {/* Session sidebar */}
      <div className="w-56 flex-shrink-0 flex flex-col bg-white rounded-xl shadow overflow-hidden">
        <div className="px-3 py-3 border-b flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Sessions
          </span>
          <button
            onClick={handleNewSession}
            className="text-xs bg-blue-600 text-white rounded px-2 py-0.5 hover:bg-blue-700"
          >
            + New
          </button>
        </div>
        <div className="flex-1 overflow-y-auto divide-y divide-gray-50">
          {sessions.length === 0 && (
            <p className="text-xs text-gray-400 text-center py-6 px-2">
              No sessions yet. Click + New to start.
            </p>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => loadSession(s.id)}
              className={`px-3 py-2.5 cursor-pointer hover:bg-gray-50 group relative ${
                activeId === s.id ? "bg-blue-50" : ""
              }`}
            >
              {renamingId === s.id ? (
                <input
                  autoFocus
                  className="w-full text-xs border rounded px-1 py-0.5"
                  value={renameValue}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => handleRenameSubmit(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleRenameSubmit(s.id);
                    if (e.key === "Escape") { setRenamingId(null); setRenameValue(""); }
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <p
                    className={`text-xs font-medium truncate ${
                      activeId === s.id ? "text-blue-700" : "text-gray-700"
                    }`}
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      setRenamingId(s.id);
                      setRenameValue(s.name || "");
                    }}
                  >
                    {s.name || "Untitled"}
                  </p>
                  <p className="text-xs text-gray-400">{fmtDate(s.updated_at)}</p>
                  <button
                    onClick={(e) => handleDelete(s.id, e)}
                    className="absolute right-2 top-2 hidden group-hover:block text-gray-300 hover:text-red-400 text-xs"
                  >
                    ×
                  </button>
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Backtest modal */}
      {backtestModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md space-y-4">
            <h2 className="text-lg font-semibold">Send to Backtest</h2>
            <div className="bg-gray-50 rounded-lg px-3 py-2 text-xs text-gray-600 max-h-32 overflow-y-auto whitespace-pre-wrap">
              {backtestModal.text.slice(0, 500)}{backtestModal.text.length > 500 ? "…" : ""}
            </div>
            <div className="grid grid-cols-2 gap-3">
              {([
                ["Symbol", "symbol", "text"],
                ["Initial Capital ($)", "initial_capital", "number"],
                ["Start Date", "start_date", "date"],
                ["End Date", "end_date", "date"],
              ] as [string, keyof typeof btForm, string][]).map(([label, key, type]) => (
                <div key={key} className="flex flex-col gap-1">
                  <label className="text-xs font-medium text-gray-500">{label}</label>
                  <input
                    type={type}
                    className="border rounded px-2 py-1.5 text-sm"
                    value={btForm[key]}
                    onChange={(e) => setBtForm((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </div>
              ))}
            </div>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setBacktestModal(null)}
                className="px-4 py-2 text-sm text-gray-600 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  const params = new URLSearchParams({
                    strategy: backtestModal.text,
                    symbol: btForm.symbol,
                    start_date: btForm.start_date,
                    end_date: btForm.end_date,
                    initial_capital: btForm.initial_capital,
                  });
                  setBacktestModal(null);
                  navigate(`/simulation?${params.toString()}`);
                }}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
              >
                Run Backtest →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Main chat panel */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-3">
          <h1 className="text-2xl font-bold">AI Trading Copilot</h1>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">Agent:</span>
            <div className="flex rounded border overflow-hidden">
              {(["auto", "advice", "research"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setAgentMode(m)}
                  className={`px-3 py-1 text-xs font-medium ${
                    agentMode === m
                      ? "bg-emerald-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50"
                  }`}
                  title={
                    m === "auto" ? "Orchestrator routes to the best specialist" :
                    m === "advice" ? "Tool-equipped investment-advice agent" :
                    "Perplexity deep-research agent"
                  }
                >
                  {m === "auto" ? "Auto" : m === "advice" ? "Advice" : "Research"}
                </button>
              ))}
            </div>
            <span className="text-gray-500">Backend:</span>
            <div className="flex rounded border overflow-hidden">
              {(["bedrock", "ollama", "ollama-cloud"] as const).map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`px-3 py-1 text-xs font-medium ${
                    provider === p
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {p === "bedrock" ? "Bedrock" :
                   p === "ollama-cloud" ? "Ollama Cloud" :
                   `Ollama${!ollamaAvailable ? " (offline)" : ""}`}
                </button>
              ))}
            </div>
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="border rounded px-2 py-1 text-xs text-gray-700 bg-white"
            >
              {modelOptions.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>

        {!activeId ? (
          <div className="flex-1 flex flex-col items-center justify-center bg-white rounded-xl shadow text-gray-400">
            <p className="text-sm mb-3">Select a session or start a new one.</p>
            <button
              onClick={handleNewSession}
              className="bg-blue-600 text-white rounded px-4 py-2 text-sm hover:bg-blue-700"
            >
              + New Session
            </button>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto bg-white rounded-xl shadow p-4 flex flex-col gap-3">
              {messages.length === 0 && (
                <p className="text-gray-400 text-sm text-center mt-8">
                  Ask anything about your portfolio, trading strategies, or financial concepts.
                </p>
              )}
              {messages.map((m, i) => (
                <div key={i} className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"}`}>
                  {m.role === "assistant" && m.intent && INTENT_LABEL[m.intent] && (
                    <span className="mb-1 text-xs font-medium text-emerald-700 bg-emerald-50 rounded px-2 py-0.5">
                      {INTENT_LABEL[m.intent]}
                    </span>
                  )}
                  <div
                    className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
                      m.role === "user"
                        ? "bg-blue-600 text-white whitespace-pre-wrap"
                        : "bg-gray-100 text-gray-900 prose prose-sm max-w-none"
                    }`}
                  >
                    {m.role === "user" ? m.text : (
                      <ReactMarkdown>{m.text}</ReactMarkdown>
                    )}
                  </div>
                  {m.role === "assistant" && (
                    <button
                      onClick={() => setBacktestModal({ text: m.text })}
                      className="mt-1 text-xs text-blue-500 hover:text-blue-700 hover:underline"
                    >
                      → Backtest this strategy
                    </button>
                  )}
                </div>
              ))}
              {loading && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-xl px-4 py-2 text-sm text-gray-500 animate-pulse">
                    Thinking…
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            <form onSubmit={send} className="mt-3 flex gap-2">
              <input
                className="flex-1 border rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. What's a good CAPM-based strategy for my portfolio?"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={loading}
              />
              {loading ? (
                <button
                  type="button"
                  onClick={handleStop}
                  className="bg-red-500 text-white rounded-xl px-5 py-2 text-sm font-medium hover:bg-red-600"
                >
                  Stop
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!input.trim()}
                  className="bg-blue-600 text-white rounded-xl px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
                >
                  Send
                </button>
              )}
            </form>
          </>
        )}
      </div>
    </div>
  );
}
