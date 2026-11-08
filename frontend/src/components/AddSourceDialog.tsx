import { useMemo, useRef, useState } from "react";
import { ingestChatGPT, ingestPerplexity, uploadDocument, apiErrorMessage } from "../api/client";
import { PERPLEXITY_DISABLED } from "../config";
import { providerSummary } from "../settings/providers";
import { useProviderSettings } from "../settings/useProviderSettings";
import Modal from "./Modal";
import ProviderControls from "./ProviderControls";

type Method = "file" | "text" | "external" | "perplexity";
type DocumentType = "fund_letter" | "principle_text";

const CHATGPT_URL = "https://chatgpt.com";

// Pre-configured deep-research prompts. `{symbol}` is substituted with the ticker.
const PROMPT_TEMPLATES = [
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

const METHODS: { key: Method; label: string; hint: string }[] = [
  { key: "file", label: "Upload file", hint: "Fund letters, PDFs, mailboxes" },
  { key: "text", label: "Paste text", hint: "An article or note you already have" },
  { key: "external", label: "Import an external answer", hint: "Paste a ChatGPT / Perplexity response" },
];

// One intake flow for every source. Fields appear only once a method is chosen, and the
// extraction model stays tucked inside the dialog instead of occupying the workspace.
export default function AddSourceDialog({ onClose, onIngested }: { onClose: () => void; onIngested: () => void }) {
  const [method, setMethod] = useState<Method | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const [title, setTitle] = useState("");
  const [source, setSource] = useState("ARK");
  const [date, setDate] = useState("");
  const [documentType, setDocumentType] = useState<DocumentType>("fund_letter");
  const [text, setText] = useState("");
  const [ticker, setTicker] = useState("");
  const [externalAnswer, setExternalAnswer] = useState("");
  const [pxTopic, setPxTopic] = useState("");
  const [pxQuery, setPxQuery] = useState("");
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);

  const providerSettings = useProviderSettings();
  const { provider, model } = providerSettings;

  const fileRef = useRef<HTMLInputElement>(null);

  const symbol = ticker.trim().toUpperCase();
  const prompts = useMemo(
    () => PROMPT_TEMPLATES.map((p) => ({ label: p.label, text: p.template.replace(/\{symbol\}/g, symbol || "the stock") })),
    [symbol],
  );

  const finish = (message: string) => {
    setStatus(message);
    onIngested();
  };

  const submitFileOrText = async () => {
    if (!title.trim()) return setError("Title is required.");

    const form = new FormData();
    form.append("title", title.trim());
    form.append("source", source.trim() || "ARK");
    form.append("document_type", documentType);
    if (date) form.append("date", date);
    form.append("provider", provider);
    form.append("model", model);

    if (method === "file") {
      const file = fileRef.current?.files?.[0];
      if (!file) return setError("Select a file.");
      form.append("file", file);
    } else {
      if (!text.trim()) return setError("Paste some text.");
      form.append("text", text.trim());
    }

    setBusy(true);
    setError("");
    try {
      const res = await uploadDocument(form);
      if (res.status === "duplicate") {
        setStatus("Already in knowledge base.");
      } else if (res.imported !== undefined) {
        finish(
          res.imported === 0
            ? `All ${res.duplicates} emails already in library.`
            : `Imported ${res.imported} email${res.imported === 1 ? "" : "s"}${
                res.duplicates ? ` (${res.duplicates} duplicates skipped)` : ""
              }. Thesis extraction running in background.`,
        );
      } else {
        finish("Added successfully.");
      }
      setTitle("");
      setDate("");
      setText("");
      if (fileRef.current) fileRef.current.value = "";
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const submitExternal = async () => {
    if (!externalAnswer.trim()) return setError("Paste the external answer first.");
    setBusy(true);
    setError("");
    try {
      const res = await ingestChatGPT({
        text: externalAnswer.trim(),
        ticker: symbol || undefined,
        provider,
        model,
      });
      if (res.status === "duplicate") {
        setStatus("Already in knowledge base.");
      } else {
        const tags = res.tags?.length ? ` Tags: ${res.tags.join(", ")}.` : "";
        const citations = res.citations_stored ? ` ${res.citations_stored} citation(s) stored.` : "";
        finish(`Saved. Expires ${res.expiration_at?.slice(0, 10) ?? "in 30 days"}.${tags}${citations}`);
        setExternalAnswer("");
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const submitPerplexity = async () => {
    if (!pxQuery.trim()) return setError("Query is required.");
    if (!pxTopic.trim()) return setError("Topic is required.");
    setBusy(true);
    setError("");
    try {
      const res = await ingestPerplexity({ query: pxQuery.trim(), topic: pxTopic.trim(), provider, model });
      if (res.status === "duplicate") {
        setStatus("Already in knowledge base.");
      } else {
        const tags = res.tags?.length ? ` Tags: ${res.tags.join(", ")}.` : "";
        const citations = res.citations_stored ? ` ${res.citations_stored} citation(s) stored.` : "";
        finish(`Saved. Expires ${res.expiration_at?.slice(0, 10) ?? "in 30 days"}.${tags}${citations}`);
        setPxQuery("");
        setPxTopic("");
      }
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const copyPrompt = async (value: string, index: number) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedIndex(index);
      setTimeout(() => setCopiedIndex((c) => (c === index ? null : c)), 1500);
    } catch {
      /* clipboard unavailable — the prompt is still visible to select manually */
    }
  };

  const methods = PERPLEXITY_DISABLED
    ? METHODS
    : [...METHODS, { key: "perplexity" as Method, label: "Perplexity query", hint: "Run a query and save the result" }];

  return (
    <Modal title="Add source" onClose={onClose}>
      {status && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{status}</p>}

      {method === null ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">Where is this research coming from?</p>
          {methods.map((m) => (
            <button
              key={m.key}
              type="button"
              onClick={() => { setMethod(m.key); setStatus(null); setError(""); }}
              className="w-full rounded-lg border border-gray-200 px-4 py-3 text-left hover:border-blue-400 hover:bg-blue-50"
            >
              <span className="block text-sm font-medium text-gray-900">{m.label}</span>
              <span className="block text-xs text-gray-500">{m.hint}</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-medium text-gray-700">
              {methods.find((m) => m.key === method)?.label}
            </span>
            <button
              type="button"
              onClick={() => { setMethod(null); setError(""); }}
              className="text-xs text-blue-600 hover:underline"
            >
              Change method
            </button>
          </div>

          {(method === "file" || method === "text") && (
            <>
              <Field label="Title" htmlFor="source-title">
                <input
                  id="source-title"
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. ARK — TSLA thesis 2025-Q2"
                />
              </Field>
              <div className="flex flex-wrap gap-3">
                <Field label="Source / Fund" htmlFor="source-fund" className="flex-1 min-w-32">
                  <input
                    id="source-fund"
                    className="w-full border rounded px-3 py-1.5 text-sm"
                    value={source}
                    onChange={(e) => setSource(e.target.value)}
                    placeholder="ARK, Scalable Capital, …"
                  />
                </Field>
                <Field label="Date" htmlFor="source-date" className="w-36">
                  <input
                    id="source-date"
                    type="date"
                    className="w-full border rounded px-3 py-1.5 text-sm"
                    value={date}
                    onChange={(e) => setDate(e.target.value)}
                  />
                </Field>
              </div>
              <Field label="Document type" htmlFor="source-type">
                <select
                  id="source-type"
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value as DocumentType)}
                >
                  <option value="fund_letter">Fund letter / Newsletter</option>
                  <option value="principle_text">Principles / Evergreen</option>
                </select>
                <p className="mt-1 text-xs text-gray-400">
                  Controls corpus classification directly and overrides source-name guessing.
                </p>
              </Field>

              {method === "file" ? (
                <Field label="File" htmlFor="source-file">
                  <input id="source-file" ref={fileRef} type="file" accept=".txt,.md,.pdf,.mbox" className="text-sm" />
                </Field>
              ) : (
                <Field label="Content" htmlFor="source-text">
                  <textarea
                    id="source-text"
                    className="w-full border rounded px-3 py-2 text-sm h-36 resize-y"
                    placeholder="Paste the article content here…"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </Field>
              )}
            </>
          )}

          {method === "external" && (
            <>
              <Field label="Ticker (optional)" htmlFor="source-ticker">
                <input
                  id="source-ticker"
                  className="w-full border rounded px-3 py-1.5 text-sm uppercase"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  placeholder="AAPL"
                />
              </Field>
              <div>
                <span className="mb-1 block text-xs font-medium text-gray-500">Deep-research prompts</span>
                <div className="space-y-2">
                  {prompts.map((p, i) => (
                    <div key={p.label} className="rounded border bg-gray-50 p-2 text-xs">
                      <p className="font-medium text-gray-600">{p.label}</p>
                      <p className="mb-2 text-gray-500">{p.text}</p>
                      <div className="flex gap-2">
                        <a
                          href={`${CHATGPT_URL}/?q=${encodeURIComponent(p.text)}`}
                          target="_blank"
                          rel="noreferrer"
                          className="rounded bg-emerald-600 px-2 py-1 text-white hover:bg-emerald-700"
                        >
                          Open in ChatGPT ↗
                        </a>
                        <button
                          type="button"
                          onClick={() => copyPrompt(p.text, i)}
                          className="rounded border border-gray-300 px-2 py-1 text-gray-600 hover:bg-gray-100"
                        >
                          {copiedIndex === i ? "Copied!" : "Copy"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <Field label="Paste the answer" htmlFor="source-answer">
                <textarea
                  id="source-answer"
                  className="w-full border rounded px-3 py-2 text-sm h-36 resize-y"
                  placeholder="Paste the completed answer here…"
                  value={externalAnswer}
                  onChange={(e) => setExternalAnswer(e.target.value)}
                />
              </Field>
            </>
          )}

          {method === "perplexity" && (
            <>
              <Field label="Topic" htmlFor="source-px-topic">
                <input
                  id="source-px-topic"
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={pxTopic}
                  onChange={(e) => setPxTopic(e.target.value)}
                  placeholder="e.g. AI Infrastructure"
                />
              </Field>
              <Field label="Research query" htmlFor="source-px-query">
                <textarea
                  id="source-px-query"
                  className="w-full border rounded px-3 py-2 text-sm h-24 resize-y"
                  value={pxQuery}
                  onChange={(e) => setPxQuery(e.target.value)}
                  placeholder="e.g. What are the latest institutional concerns about AI capex saturation?"
                />
              </Field>
            </>
          )}

          <details className="text-xs">
            <summary className="cursor-pointer text-gray-500">
              Extraction model: {providerSummary(providerSettings)}
            </summary>
            <div className="mt-2">
              <ProviderControls settings={providerSettings} label="Extraction model" />
            </div>
          </details>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-50"
            >
              Close
            </button>
            <button
              type="button"
              onClick={
                method === "file" || method === "text"
                  ? submitFileOrText
                  : method === "external"
                  ? submitExternal
                  : submitPerplexity
              }
              disabled={busy}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? "Saving…" : "Add to library"}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

function Field({
  label,
  htmlFor,
  className = "",
  children,
}: {
  label: string;
  htmlFor: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="mb-1 block text-xs font-medium text-gray-500">
        {label}
      </label>
      {children}
    </div>
  );
}
