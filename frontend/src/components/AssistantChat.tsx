import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import {
  agentChat,
  createSession,
  deleteSession,
  getSessionMessages,
  listSessions,
  renameSession,
} from "../api/client";
import type { PortfolioTradeHandoff, StrategyDraftHandoff } from "../api/handoffs";
import { useAssistantContext } from "../assistant/useAssistantContext";
import { PERPLEXITY_DISABLED } from "../config";
import { PROVIDER_ORDER, providerSummary, type Provider } from "../settings/providers";
import { useProviderSettings, type ProviderSettingsApi } from "../settings/useProviderSettings";
import ProposalCard, { type Proposal } from "./ProposalCard";
import ProviderControls from "./ProviderControls";

interface Message {
  role: "user" | "assistant";
  text: string;
  intent?: string; // which specialist answered: research | advice | both
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

const LAST_SESSION_KEY = "quant.assistant.sessionId";

function readLastSession(): string | null {
  try {
    return localStorage.getItem(LAST_SESSION_KEY);
  } catch {
    return null;
  }
}

function writeLastSession(id: string | null): void {
  try {
    if (id) localStorage.setItem(LAST_SESSION_KEY, id);
    else localStorage.removeItem(LAST_SESSION_KEY);
  } catch {
    /* storage is a convenience — the session list still works */
  }
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// The one conversation implementation. The legacy /agent route shows it full page;
// the contextual panel shows the same component with the session list collapsed.
export default function AssistantChat({ compact = false }: { compact?: boolean }) {
  const navigate = useNavigate();
  const { items, detach, close } = useAssistantContext();
  const settings = useProviderSettings();

  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(readLastSession);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState<AgentMode>("auto");
  const [showSessions, setShowSessions] = useState(!compact);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [sessionError, setSessionError] = useState("");
  const [sendError, setSendError] = useState("");
  // A stored session keeps its own provider/model until the user changes them here.
  const [sessionModel, setSessionModel] = useState<{ provider: Provider; model: string } | null>(null);

  const [multiSymbol, setMultiSymbol] = useState("");
  const [multiRunning, setMultiRunning] = useState(false);
  const [multiPhases, setMultiPhases] = useState<Record<string, string>>({});
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [multiError, setMultiError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const effectiveProvider = sessionModel?.provider ?? settings.provider;
  const effectiveModel =
    sessionModel?.model || settings.catalog[effectiveProvider]?.[0] || settings.model;
  const providerSettings: ProviderSettingsApi = {
    ...settings,
    provider: effectiveProvider,
    model: effectiveModel,
    changeProvider: (next) => {
      setSessionModel(null);
      settings.changeProvider(next);
    },
    changeModel: (next) => {
      setSessionModel(null);
      settings.changeModel(next);
    },
  };
  const { provider, model } = providerSettings;

  const refreshSessions = async () => {
    try {
      const data = await listSessions();
      setSessions(data.sessions);
      setSessionError("");
    } catch {
      setSessionError("Could not load saved conversations.");
    }
  };

  const scrollToBottom = () => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  const loadSession = async (id: string) => {
    setActiveId(id);
    writeLastSession(id);
    setMessages([]);
    setSendError("");
    try {
      const data = await getSessionMessages(id);
      const mapped: Message[] = (data.history || []).map((m: { role: string; content: { text?: string }[] }) => ({
        role: m.role as "user" | "assistant",
        text: m.content.map((c) => c.text || "").join(""),
      }));
      setMessages(mapped);
      setSessionError("");
      const nextProvider = (data.provider as Provider) || "router";
      if (!PROVIDER_ORDER.includes(nextProvider)) {
        // Unknown provider from an older session — fall back to shared settings.
        setSessionModel(null);
      } else {
        const catalog = settings.catalog[nextProvider] ?? [];
        // A model retired from the catalog can't be restored — use the verified default.
        const requested = data.model ?? "";
        const retired = catalog.length > 0 && !catalog.includes(requested);
        const restored = retired || !requested ? (catalog[0] ?? "") : requested;
        setSessionModel({ provider: nextProvider, model: restored });
      }
    } catch {
      setSessionError("Could not load this conversation. It may have been deleted.");
      setMessages([]);
      setActiveId(null);
      writeLastSession(null);
    }
    scrollToBottom();
  };

  useEffect(() => {
    void refreshSessions();
    const last = readLastSession();
    if (last) void loadSession(last);
    // Mount-only: later session selections come from the list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleNewSession = async () => {
    try {
      const data = await createSession(undefined, provider, model || undefined);
      await refreshSessions();
      setSessionModel(null);
      await loadSession(data.id);
      setMessages([]);
    } catch {
      setSessionError("Could not start a new conversation.");
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deleteSession(id);
    } catch {
      setSessionError("Could not delete that conversation.");
      return;
    }
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
      writeLastSession(null);
    }
    await refreshSessions();
  };

  const handleRenameSubmit = async (id: string) => {
    try {
      if (renameValue.trim()) await renameSession(id, renameValue.trim());
    } catch {
      setSessionError("Could not rename that conversation.");
    }
    setRenamingId(null);
    setRenameValue("");
    await refreshSessions();
  };

  // Sending without a session starts one, so the panel never blocks on setup.
  const ensureSession = async (): Promise<string | null> => {
    if (activeId) return activeId;
    try {
      const data = await createSession(undefined, provider, model || undefined);
      setActiveId(data.id);
      writeLastSession(data.id);
      await refreshSessions();
      return data.id;
    } catch {
      setSendError("Could not start a conversation. Check that the backend is running.");
      return null;
    }
  };

  const send = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    const sessionId = await ensureSession();
    if (!sessionId) return;

    setInput("");
    setSendError("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const data = await agentChat(
        text,
        sessionId,
        provider,
        model || undefined,
        ctrl.signal,
        mode,
        items.map(({ label, value }) => ({ label, value })),
      );
      setMessages((prev) => [...prev, { role: "assistant", text: data.reply, intent: data.intent }]);
      await refreshSessions();
    } catch (err) {
      const isCanceled =
        (err as { name?: string; code?: string }).name === "CanceledError" ||
        (err as { code?: string }).code === "ERR_CANCELED";
      if (isCanceled) {
        setMessages((prev) => prev.slice(0, -1));
        setInput(text);
      } else {
        const detail = (err as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail;
        setMessages((prev) => [
          ...prev,
          { role: "assistant", text: `Error: ${detail ?? (err as Error).message}` },
        ]);
      }
    } finally {
      abortRef.current = null;
      setLoading(false);
      scrollToBottom();
    }
  };

  const handleMultiRun = async () => {
    if (!multiSymbol.trim() || multiRunning) return;
    setMultiRunning(true);
    setMultiPhases({});
    setProposal(null);
    setMultiError(null);

    try {
      const resp = await fetch("/api/agent/multi-run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: multiSymbol.trim().toUpperCase(),
          provider,
          model: model || null,
          session_id: activeId || "",
        }),
      });
      if (!resp.ok) throw new Error(`Server error: ${resp.status}`);

      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No response stream");

      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.phase === "error") {
              setMultiError(event.error ?? "Unknown error");
            } else if (event.phase === "complete" && event.result) {
              setProposal(event.result as Proposal);
              setMultiPhases((prev) => ({ ...prev, complete: "complete" }));
            } else if (event.phase && event.status) {
              setMultiPhases((prev) => ({ ...prev, [event.phase]: event.status }));
            }
          } catch {
            // ignore parse errors on partial frames
          }
        }
      }
    } catch (err) {
      setMultiError((err as Error).message ?? "Request failed");
    } finally {
      setMultiRunning(false);
    }
  };

  const openInStrategies = (strategyText: string) => {
    navigate("/strategies", { state: { strategy: strategyText } satisfies StrategyDraftHandoff });
    close();
  };

  const reviewProposalTrade = (action: string, symbol: string, sizePct: number) => {
    navigate("/portfolio", {
      state: {
        prefillAction: action.toUpperCase() === "SELL" ? "SELL" : "BUY",
        prefillSymbol: symbol,
        prefillSizePct: sizePct,
        decisionContext: {
          provider,
          model: model || undefined,
          session_id: activeId ?? undefined,
        },
      } satisfies PortfolioTradeHandoff,
    });
    close();
  };

  const sessionRow = (s: Session) => (
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
            if (e.key === "Escape") {
              setRenamingId(null);
              setRenameValue("");
            }
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <>
          <p
            className={`text-xs font-medium truncate ${activeId === s.id ? "text-blue-700" : "text-gray-700"}`}
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
            aria-label={`Delete ${s.name || "untitled"} conversation`}
            className="absolute right-2 top-2 hidden group-hover:block text-gray-300 hover:text-red-400 text-xs"
          >
            ×
          </button>
        </>
      )}
    </div>
  );

  return (
    <div className={compact ? "flex h-full min-h-0 flex-col" : "flex h-[calc(100vh-96px)] gap-4"}>
      {showSessions && !compact && (
        <div className="w-56 flex-shrink-0 flex flex-col bg-white rounded-xl shadow overflow-hidden">
          <div className="px-3 py-3 border-b flex items-center justify-between">
            <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Sessions</span>
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
                No sessions yet. Ask a question to start one.
              </p>
            )}
            {sessions.map(sessionRow)}
          </div>
        </div>
      )}

      <div className="flex-1 flex flex-col min-w-0 min-h-0">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <h1 className={compact ? "text-lg font-bold" : "text-2xl font-bold"}>Ask AI</h1>
            {compact && (
              <button
                type="button"
                onClick={() => setShowSessions((v) => !v)}
                aria-expanded={showSessions}
                className="rounded border border-gray-200 px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-50"
              >
                {showSessions ? "Hide sessions" : "Sessions"}
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={handleNewSession}
            className="rounded border border-gray-200 px-3 py-1 text-xs text-gray-600 hover:bg-gray-50"
          >
            + New chat
          </button>
        </div>

        {compact && showSessions && (
          <div className="mt-2 max-h-40 overflow-y-auto rounded-xl border bg-white divide-y">
            {sessions.length === 0 ? (
              <p className="px-3 py-3 text-xs text-gray-400">No sessions yet. Ask a question to start one.</p>
            ) : (
              sessions.map(sessionRow)
            )}
          </div>
        )}

        <details className="mt-2 rounded border bg-white px-3 py-2 text-xs">
          <summary className="cursor-pointer text-gray-500">Model: {providerSummary(providerSettings)}</summary>
          <div className="mt-2 space-y-2">
            <ProviderControls settings={providerSettings} />
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-gray-500">Task:</span>
              <div className="flex overflow-hidden rounded border">
                {(["auto", "advice", "research"] as const).map((m) => {
                  const disabled = m === "research" && PERPLEXITY_DISABLED;
                  return (
                    <button
                      key={m}
                      type="button"
                      onClick={() => !disabled && setMode(m)}
                      disabled={disabled}
                      aria-pressed={mode === m}
                      title={
                        disabled
                          ? "Deep research via Perplexity is disabled. Use Add source on the Research page."
                          : m === "auto"
                            ? "Let the assistant choose the best specialist"
                            : m === "advice"
                              ? "Tool-equipped investment-advice agent"
                              : "Perplexity deep-research agent"
                      }
                      className={`px-3 py-1 text-xs font-medium disabled:cursor-not-allowed disabled:opacity-40 ${
                        mode === m ? "bg-emerald-600 text-white" : "bg-white text-gray-600 hover:bg-gray-50"
                      }`}
                    >
                      {m === "auto" ? "Auto" : m === "advice" ? "Advice" : "Research"}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </details>
        {settings.notice && (
          <p role="status" className="mt-1 text-xs text-amber-600">
            {settings.notice}
          </p>
        )}

        <details className="mt-2 rounded border bg-white px-3 py-2 text-xs">
          <summary className="cursor-pointer text-gray-500">Analyze a company (multi-agent)</summary>
          <div className="mt-2 flex gap-2">
            <input
              className="border rounded-lg px-3 py-1.5 text-sm w-32 uppercase focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="AAPL"
              aria-label="Ticker to analyze"
              value={multiSymbol}
              onChange={(e) => setMultiSymbol(e.target.value.toUpperCase())}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleMultiRun();
              }}
              disabled={multiRunning}
            />
            <button
              type="button"
              onClick={handleMultiRun}
              disabled={!multiSymbol.trim() || multiRunning}
              className="bg-indigo-600 text-white rounded-lg px-4 py-1.5 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {multiRunning ? "Analyzing…" : "Analyze"}
            </button>
            {(proposal || multiError) && !multiRunning && (
              <button
                type="button"
                onClick={() => {
                  setProposal(null);
                  setMultiError(null);
                  setMultiPhases({});
                }}
                className="text-xs text-gray-400 hover:text-gray-600 px-2"
              >
                Clear
              </button>
            )}
          </div>

          {multiRunning && <p className="mt-2 text-gray-500">Running analysts → debate → trader → risk…</p>}

          {(multiRunning || Object.keys(multiPhases).length > 0) && (
            <details className="mt-2 text-gray-500">
              <summary className="cursor-pointer">Run details</summary>
              <div className="mt-1 flex flex-wrap gap-2">
                {[
                  { key: "analysts", label: "Analysts" },
                  { key: "debate", label: "Debate" },
                  { key: "trader", label: "Trader" },
                  { key: "risk", label: "Risk" },
                ].map(({ key, label }) => {
                  const status = multiPhases[key];
                  return (
                    <span
                      key={key}
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        status === "complete"
                          ? "bg-emerald-100 text-emerald-700"
                          : status === "running"
                            ? "bg-blue-100 text-blue-700 animate-pulse"
                            : "bg-gray-100 text-gray-400"
                      }`}
                    >
                      {status === "complete" ? "✓ " : status === "running" ? "⟳ " : ""}
                      {label}
                    </span>
                  );
                })}
              </div>
            </details>
          )}

          {multiError && <p className="mt-2 text-xs text-red-600">Error: {multiError}</p>}
        </details>

        {proposal && (
          <div className="mt-2">
            <ProposalCard
              proposal={proposal}
              onDismiss={() => setProposal(null)}
              onAddToPortfolio={reviewProposalTrade}
            />
          </div>
        )}

        {sessionError && (
          <p role="status" className="mt-2 rounded bg-amber-50 px-3 py-2 text-xs text-amber-700">
            {sessionError}
          </p>
        )}

        <div className="mt-2 flex-1 min-h-0 overflow-y-auto bg-white rounded-xl shadow p-4 flex flex-col gap-3">
          {messages.length === 0 && (
            <p className="text-gray-400 text-sm text-center mt-8">
              Ask about your portfolio, a company you are researching, or a strategy.
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
                {m.role === "user" ? m.text : <ReactMarkdown>{m.text}</ReactMarkdown>}
              </div>
              {m.role === "assistant" && (
                <button
                  type="button"
                  onClick={() => openInStrategies(m.text)}
                  className="mt-1 text-xs text-blue-500 hover:text-blue-700 hover:underline"
                >
                  → Open in Strategies
                </button>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-gray-100 rounded-xl px-4 py-2 text-sm text-gray-500 animate-pulse">Thinking…</div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {items.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1" aria-label="Attached context">
            {items.map((item) => (
              <span
                key={item.id}
                title={item.value}
                className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
              >
                {item.label}
                <button
                  type="button"
                  onClick={() => detach(item.id)}
                  aria-label={`Remove ${item.label} context`}
                  className="text-blue-400 hover:text-blue-700"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}

        {sendError && (
          <p role="alert" className="mt-2 text-xs text-red-600">
            {sendError}
          </p>
        )}

        <form onSubmit={send} className="mt-2 flex gap-2">
          <input
            className="flex-1 border rounded-xl px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="e.g. What is the main risk in my largest position?"
            aria-label="Message the assistant"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
          />
          {loading ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
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
      </div>
    </div>
  );
}
