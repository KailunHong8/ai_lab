import { useMemo, useState } from "react";
import { ingestChatGPT } from "../api/client";

type Provider = "bedrock" | "ollama" | "ollama-cloud";

interface Props {
  provider: Provider;
  model: string;
  onIngested?: () => void;
}

// Pre-configured deep-research prompts. `{symbol}` is substituted with the ticker.
const PROMPT_TEMPLATES: { label: string; template: string }[] = [
  {
    label: "Sentiment & catalysts",
    template:
      "Search real-time: Analyze recent market sentiment, analyst ratings, and time-sensitive catalysts for {symbol}. Include source links.",
  },
  {
    label: "Supply chain & competition",
    template:
      "What are the current supply chain challenges and competitive threats facing {symbol}? Cite recent sources with links.",
  },
  {
    label: "Bull vs bear thesis",
    template:
      "Summarize the strongest bull and bear thesis for {symbol} right now, grounded in the latest earnings, guidance, and news. Include source links.",
  },
];

const CHATGPT_BASE = "https://chatgpt.com";

export default function ChatGPTResearchPane({ provider, model, onIngested }: Props) {
  const [ticker, setTicker] = useState("");
  const [iframeQuery, setIframeQuery] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showSetup, setShowSetup] = useState(false);

  const symbol = ticker.trim().toUpperCase();

  const prompts = useMemo(
    () =>
      PROMPT_TEMPLATES.map((p) => ({
        label: p.label,
        text: p.template.replace(/\{symbol\}/g, symbol || "the stock"),
      })),
    [symbol],
  );

  // Seed the iframe with the first prompt as a ?q= query so ChatGPT pre-fills its box.
  const iframeSrc = iframeQuery
    ? `${CHATGPT_BASE}/?q=${encodeURIComponent(iframeQuery)}`
    : CHATGPT_BASE;

  const seedIframe = (text: string) => setIframeQuery(text);

  const copyPrompt = async (text: string, idx: number) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx((c) => (c === idx ? null : c)), 1500);
    } catch {
      /* clipboard unavailable — user can still select the text manually */
    }
  };

  const handleIngest = async () => {
    if (!pasteText.trim()) return setStatus("Paste a ChatGPT response first.");
    setLoading(true);
    setStatus(null);
    try {
      const res = await ingestChatGPT({
        text: pasteText.trim(),
        ticker: symbol || undefined,
        provider,
        model,
      });
      if (res.status === "duplicate") {
        setStatus("Already in knowledge base.");
      } else {
        const tagStr = res.tags?.length ? ` Tags: ${res.tags.join(", ")}.` : "";
        const citeStr = res.citations_stored ? ` ${res.citations_stored} citation(s) stored.` : "";
        setStatus(`Saved. Expires ${res.expiration_at?.slice(0, 10) ?? "in 30 days"}.${tagStr}${citeStr}`);
        setPasteText("");
        onIngested?.();
      }
    } catch (err: any) {
      setStatus(`Error: ${err.response?.data?.detail ?? err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white rounded-xl shadow p-6">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-semibold text-lg">ChatGPT Go Research</h2>
        <button
          type="button"
          onClick={() => setShowSetup((s) => !s)}
          className="text-xs text-blue-500 hover:text-blue-700"
        >
          {showSetup ? "Hide setup" : "Setup help"}
        </button>
      </div>
      <p className="text-xs text-gray-400 mb-4">
        Query ChatGPT Go side-by-side, then paste the answer to index it (30-day TTL).
      </p>

      {showSetup && (
        <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 space-y-1">
          <p className="font-medium">One-time browser setup to embed ChatGPT</p>
          <p>
            OpenAI blocks iframe embedding via <code>X-Frame-Options</code> /{" "}
            <code>Content-Security-Policy</code>. To view ChatGPT in the right pane, install a
            header-stripping Chrome extension (e.g.{" "}
            <a
              className="underline"
              href="https://chromewebstore.google.com/detail/ignore-x-frame-options/ammcjofgjnidafidbbaidgpfegajnjee"
              target="_blank"
              rel="noreferrer"
            >
              Ignore X-Frame-Options
            </a>{" "}
            or{" "}
            <a className="underline" href="https://github.com/suzp/HeaderEditor" target="_blank" rel="noreferrer">
              Header Editor
            </a>
            ) and configure it to strip those headers for the <code>localhost</code> origin only.
            It renders using your active Chrome ChatGPT session.
          </p>
          <p>
            Optional: install the "Send to Quant" userscript (see{" "}
            <code>docs/chatgpt_send_to_quant.user.js</code>) to push answers with one click.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* ── Left: Quant tools ─────────────────────────────────────────────── */}
        <div className="space-y-4">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Ticker</label>
            <input
              className="w-full border rounded px-3 py-1.5 text-sm uppercase"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="e.g. AAPL"
            />
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-1">Deep-research prompts</label>
            <div className="space-y-2">
              {prompts.map((p, i) => (
                <div key={i} className="border rounded p-2 text-xs bg-gray-50">
                  <p className="font-medium text-gray-600 mb-1">{p.label}</p>
                  <p className="text-gray-500 mb-2">{p.text}</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => seedIframe(p.text)}
                      className="px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                    >
                      Send to ChatGPT →
                    </button>
                    <button
                      type="button"
                      onClick={() => copyPrompt(p.text, i)}
                      className="px-2 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-100"
                    >
                      {copiedIdx === i ? "Copied!" : "Copy"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs text-gray-500 block mb-1">Paste ChatGPT response</label>
            <textarea
              className="w-full border rounded px-3 py-2 text-sm h-40 resize-y"
              placeholder="Paste ChatGPT's completed answer here…"
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
            />
          </div>

          {status && (
            <p className={`text-sm ${status.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
              {status}
            </p>
          )}

          <button
            type="button"
            onClick={handleIngest}
            disabled={loading}
            className="bg-indigo-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Ingesting…" : "Ingest into Quant DB"}
          </button>
        </div>

        {/* ── Right: embedded ChatGPT ───────────────────────────────────────── */}
        <div className="flex flex-col">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-gray-500">Live ChatGPT Go</span>
            <a
              href={iframeSrc}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-blue-500 hover:text-blue-700"
            >
              Open in tab ↗
            </a>
          </div>
          <iframe
            title="ChatGPT Go"
            src={iframeSrc}
            className="w-full border rounded-lg bg-gray-50"
            style={{ minHeight: 520, height: "100%" }}
          />
          <p className="text-xs text-gray-400 mt-1">
            Blank pane? Install a header-stripping extension for localhost (see "Setup help").
          </p>
        </div>
      </div>
    </div>
  );
}
