import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { uploadDocument, listDocuments, deleteDocument, listOllamaModels, ingestPerplexity } from "../api/client";
import ChatGPTResearchPane from "../components/ChatGPTResearchPane";
import { PERPLEXITY_DISABLED } from "../config";

interface Doc {
  id: string;
  title: string;
  source: string;
  date: string | null;
  processed: boolean;
  corpus: string | null;
  source_type: string | null;
  fund: string | null;
  recency_flag: string | null;
  reliability_tier: number | null;
  expiration_at: string | null;
}

type UploadDocumentType = "fund_letter" | "principle_text";

const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];
const OLLAMA_CLOUD_MODELS = ["gpt-oss:120b", "gemma4:31b"];

const RECENCY_BADGE: Record<string, string> = {
  evergreen: "bg-green-100 text-green-700",
  timely:    "bg-blue-100 text-blue-700",
  stale:     "bg-gray-100 text-gray-500",
};

const CORPUS_LABEL: Record<string, string> = {
  principles:     "Principles",
  market_opinion: "Market",
};

export default function Research() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [corpusFilter, setCorpusFilter] = useState<"all" | "principles" | "market_opinion">("all");

  // Upload form state
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("ARK");
  const [documentType, setDocumentType] = useState<UploadDocumentType>("fund_letter");
  const [date, setDate] = useState("");
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"file" | "text">("file");
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);

  // Perplexity ingest state
  const [pxQuery, setPxQuery] = useState("");
  const [pxTopic, setPxTopic] = useState("");
  const [pxStatus, setPxStatus] = useState<string | null>(null);
  const [pxLoading, setPxLoading] = useState(false);

  // Provider/model state (shared by both panels)
  const [provider, setProvider] = useState<"bedrock" | "ollama" | "ollama-cloud">("bedrock");
  const [model, setModel] = useState<string>(BEDROCK_MODELS[0]);
  const [ollamaModels, setOllamaModels] = useState<string[]>(["qwen2.5:9b"]);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);

  const [cleanupStatus, setCleanupStatus] = useState<string | null>(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);

  const fileRef = useRef<HTMLInputElement>(null);

  const load = async () => {
    try {
      setDocs(await listDocuments());
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    load();
    listOllamaModels()
      .then((data: { models: string[]; available: boolean }) => {
        setOllamaAvailable(data.available);
        if (data.models.length > 0) setOllamaModels(data.models);
      })
      .catch(() => {});
  }, []);

  const handleProviderChange = (p: "bedrock" | "ollama" | "ollama-cloud") => {
    setProvider(p);
    if (p === "bedrock") setModel(BEDROCK_MODELS[0]);
    else if (p === "ollama-cloud") setModel(OLLAMA_CLOUD_MODELS[0]);
    else setModel(ollamaModels[0] || "qwen2.5:9b");
  };

  const modelOptions =
    provider === "bedrock" ? BEDROCK_MODELS :
    provider === "ollama-cloud" ? OLLAMA_CLOUD_MODELS :
    ollamaModels;

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return setUploadStatus("Title is required.");

    const fd = new FormData();
    fd.append("title", title.trim());
    fd.append("source", source.trim() || "ARK");
    fd.append("document_type", documentType);
    if (date) fd.append("date", date);
    fd.append("provider", provider);
    fd.append("model", model);

    if (tab === "file") {
      const file = fileRef.current?.files?.[0];
      if (!file) return setUploadStatus("Select a file.");
      fd.append("file", file);
    } else {
      if (!text.trim()) return setUploadStatus("Paste some text.");
      fd.append("text", text.trim());
    }

    setUploadLoading(true);
    setUploadStatus(null);
    try {
      const res = await uploadDocument(fd);
      if (res.status === "duplicate") {
        setUploadStatus("Already in knowledge base.");
      } else if (res.imported !== undefined) {
        const msg =
          res.imported === 0
            ? `All ${res.duplicates} emails already in library.`
            : `Imported ${res.imported} email${res.imported !== 1 ? "s" : ""}${
                res.duplicates ? ` (${res.duplicates} duplicates skipped)` : ""
              }. Thesis extraction running in background.`;
        setUploadStatus(msg);
        setTitle("");
        setDate("");
        if (fileRef.current) fileRef.current.value = "";
        await load();
      } else {
        setUploadStatus("Added successfully.");
        setTitle("");
        setDate("");
        setText("");
        if (fileRef.current) fileRef.current.value = "";
        await load();
      }
    } catch (err: any) {
      setUploadStatus(`Error: ${err.response?.data?.detail ?? err.message}`);
    } finally {
      setUploadLoading(false);
    }
  };

  const handlePerplexityIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pxQuery.trim()) return setPxStatus("Query is required.");
    if (!pxTopic.trim()) return setPxStatus("Topic is required.");

    setPxLoading(true);
    setPxStatus(null);
    try {
      const res = await ingestPerplexity({ query: pxQuery.trim(), topic: pxTopic.trim(), provider, model });
      if (res.status === "duplicate") {
        setPxStatus("Already in knowledge base.");
      } else {
        const tagStr = res.tags?.length ? ` Tags: ${res.tags.join(", ")}.` : "";
        const citeStr = res.citations_stored ? ` ${res.citations_stored} citation(s) stored.` : "";
        setPxStatus(`Saved. Expires ${res.expiration_at?.slice(0, 10) ?? "in 30 days"}.${tagStr}${citeStr}`);
        setPxQuery("");
        setPxTopic("");
        await load();
      }
    } catch (err: any) {
      setPxStatus(`Error: ${err.response?.data?.detail ?? err.message}`);
    } finally {
      setPxLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    await deleteDocument(id);
    setDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const handleCleanup = async () => {
    setCleanupLoading(true);
    setCleanupStatus(null);
    try {
      const res = await axios.delete("/api/knowledge/cleanup-stale");
      const { removed } = res.data;
      setCleanupStatus(removed === 0 ? "No expired research found." : `Removed ${removed} expired document(s).`);
      await load();
    } catch (err: any) {
      setCleanupStatus(`Error: ${err.response?.data?.detail ?? err.message}`);
    } finally {
      setCleanupLoading(false);
    }
  };

  const filteredDocs = docs.filter((d) => {
    if (corpusFilter === "all") return true;
    return d.corpus === corpusFilter;
  });

  const principlesCount = docs.filter((d) => d.corpus === "principles").length;
  const marketCount = docs.filter((d) => d.corpus === "market_opinion").length;

  // ── Provider selector (shared) ────────────────────────────────────────────────
  const ProviderBar = () => (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-xs text-gray-500">Extract with:</span>
      <div className="flex rounded border overflow-hidden">
        {(["bedrock", "ollama", "ollama-cloud"] as const).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => handleProviderChange(p)}
            className={`px-3 py-1 text-xs font-medium ${
              provider === p
                ? "bg-blue-600 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            {p === "bedrock" ? "Bedrock" : p === "ollama-cloud" ? "Ollama Cloud" : `Ollama${!ollamaAvailable ? " (offline)" : ""}`}
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
  );

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Research Library</h1>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* ── Manual upload ─────────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl shadow p-6">
          <h2 className="font-semibold text-lg mb-1">Add Article</h2>
          <p className="text-xs text-gray-400 mb-4">Fund letters, principles docs, newsletters</p>
          <form onSubmit={handleUpload} className="space-y-4">
            <div className="flex gap-3 flex-wrap">
              <div className="flex-1 min-w-40">
                <label className="text-xs text-gray-500 block mb-1">Title *</label>
                <input
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. ARK — TSLA thesis 2025-Q2"
                />
              </div>
              <div className="w-32">
                <label className="text-xs text-gray-500 block mb-1">Source / Fund</label>
                <input
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  placeholder="ARK, Scalable Capital, …"
                />
              </div>
              <div className="w-36">
                <label className="text-xs text-gray-500 block mb-1">Date</label>
                <input
                  type="date"
                  className="w-full border rounded px-3 py-1.5 text-sm"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-gray-500 block mb-1">Document type</label>
              <div className="flex rounded border overflow-hidden w-fit text-xs">
                {([
                  { value: "fund_letter", label: "Fund letter / Newsletter" },
                  { value: "principle_text", label: "Principles / Evergreen" },
                ] as const).map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setDocumentType(opt.value)}
                    className={`px-3 py-1.5 font-medium ${
                      documentType === opt.value
                        ? "bg-blue-600 text-white"
                        : "bg-white text-gray-600 hover:bg-gray-50"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className="text-xs text-gray-400 mt-1">
                This setting controls corpus/type classification directly and overrides source-name guessing.
              </p>
            </div>

            <ProviderBar />

            <div className="flex gap-2 text-sm">
              <button
                type="button"
                onClick={() => setTab("file")}
                className={`px-3 py-1 rounded ${tab === "file" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700"}`}
              >
                Upload file
              </button>
              <button
                type="button"
                onClick={() => setTab("text")}
                className={`px-3 py-1 rounded ${tab === "text" ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-700"}`}
              >
                Paste text
              </button>
            </div>

            {tab === "file" ? (
              <input ref={fileRef} type="file" accept=".txt,.md,.pdf,.mbox" className="text-sm" />
            ) : (
              <textarea
                className="w-full border rounded px-3 py-2 text-sm h-36 resize-y"
                placeholder="Paste the article content here…"
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            )}

            {uploadStatus && (
              <p className={`text-sm ${uploadStatus.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
                {uploadStatus}
              </p>
            )}

            <button
              type="submit"
              disabled={uploadLoading}
              className="bg-blue-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {uploadLoading ? "Adding…" : "Add to library"}
            </button>
          </form>
        </div>

        {/* ── Perplexity ingest ──────────────────────────────────────────────── */}
        <div className="bg-white rounded-xl shadow p-6 relative">
          <h2 className="font-semibold text-lg mb-1">Perplexity Research</h2>
          <p className="text-xs text-gray-400 mb-4">
            Run a query, persist findings as market context (30-day TTL)
          </p>
          {PERPLEXITY_DISABLED && (
            <div className="absolute inset-0 z-10 rounded-xl bg-white/70 backdrop-blur-[1px] flex items-center justify-center p-6">
              <div className="text-center max-w-xs">
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-200 text-gray-600">
                  Disabled
                </span>
                <p className="text-sm text-gray-500 mt-2">
                  Perplexity Pro is inactive. Use the ChatGPT Go pane below. Re-enable by setting{" "}
                  <code>DISABLE_PERPLEXITY=false</code>.
                </p>
              </div>
            </div>
          )}
          <fieldset disabled={PERPLEXITY_DISABLED} className={PERPLEXITY_DISABLED ? "pointer-events-none" : ""}>
          <form onSubmit={handlePerplexityIngest} className="space-y-4">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Topic *</label>
              <input
                className="w-full border rounded px-3 py-1.5 text-sm"
                value={pxTopic}
                onChange={(e) => setPxTopic(e.target.value)}
                placeholder="e.g. AI Infrastructure"
              />
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Research Query *</label>
              <textarea
                className="w-full border rounded px-3 py-2 text-sm h-24 resize-y"
                placeholder="e.g. What are the latest institutional concerns about AI capex saturation in semiconductors?"
                value={pxQuery}
                onChange={(e) => setPxQuery(e.target.value)}
              />
            </div>

            <ProviderBar />

            {pxStatus && (
              <p className={`text-sm ${pxStatus.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
                {pxStatus}
              </p>
            )}

            <button
              type="submit"
              disabled={pxLoading}
              className="bg-indigo-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {pxLoading ? "Researching…" : "Run & Save to Library"}
            </button>
          </form>
          </fieldset>
        </div>
      </div>

      {/* ── Embedded ChatGPT Go split-pane ─────────────────────────────────── */}
      <ChatGPTResearchPane provider={provider} model={model} onIngested={load} />

      {/* ── Document list ────────────────────────────────────────────────────── */}
      <div className="bg-white rounded-xl shadow p-6">
        {/* Corpus filter tabs + cleanup action */}
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold text-lg">Library ({docs.length})</h2>
            <div className="flex items-center gap-2">
              <button
                onClick={handleCleanup}
                disabled={cleanupLoading}
                className="text-xs px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              >
                {cleanupLoading ? "Cleaning…" : "Clean expired research"}
              </button>
              {cleanupStatus && (
                <span className={`text-xs ${cleanupStatus.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
                  {cleanupStatus}
                </span>
              )}
            </div>
          </div>
          <div className="flex rounded border overflow-hidden text-xs">
            {(["all", "principles", "market_opinion"] as const).map((c) => {
              const label =
                c === "all" ? `All (${docs.length})` :
                c === "principles" ? `Principles (${principlesCount})` :
                `Market Opinion (${marketCount})`;
              return (
                <button
                  key={c}
                  onClick={() => setCorpusFilter(c)}
                  className={`px-3 py-1.5 font-medium ${
                    corpusFilter === c
                      ? "bg-blue-600 text-white"
                      : "bg-white text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        {filteredDocs.length === 0 ? (
          <p className="text-sm text-gray-400">No articles yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="pb-2 font-medium">Title</th>
                <th className="pb-2 font-medium">Corpus</th>
                <th className="pb-2 font-medium">Source / Fund</th>
                <th className="pb-2 font-medium">Type</th>
                <th className="pb-2 font-medium">Tier</th>
                <th className="pb-2 font-medium">Freshness</th>
                <th className="pb-2 font-medium">Date / Expiry</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filteredDocs.map((d) => {
                const now = new Date();
                const expired = d.expiration_at ? new Date(d.expiration_at) <= now : false;
                return (
                  <tr key={d.id} className={`border-b last:border-0 hover:bg-gray-50 ${expired ? "opacity-60" : ""}`}>
                    <td className="py-2 pr-4 max-w-xs truncate" title={d.title}>{d.title}</td>
                    <td className="py-2 pr-3">
                      {d.corpus ? (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          d.corpus === "principles"
                            ? "bg-purple-100 text-purple-700"
                            : "bg-orange-100 text-orange-700"
                        }`}>
                          {CORPUS_LABEL[d.corpus] ?? d.corpus}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-gray-500">{d.fund || d.source}</td>
                    <td className="py-2 pr-3 text-gray-500 text-xs">{d.source_type ?? "—"}</td>
                    <td className="py-2 pr-3 text-gray-500 text-xs">{d.reliability_tier ?? "—"}</td>
                    <td className="py-2 pr-3">
                      {expired ? (
                        <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-600">expired</span>
                      ) : d.recency_flag ? (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${RECENCY_BADGE[d.recency_flag] ?? "bg-gray-100 text-gray-500"}`}>
                          {d.recency_flag}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="py-2 pr-4 text-gray-500 whitespace-nowrap text-xs">
                      {d.expiration_at ? (
                        <span title={`Expires ${d.expiration_at.slice(0, 10)}`}>
                          {d.date ?? "—"} · exp {d.expiration_at.slice(0, 10)}
                        </span>
                      ) : d.date ?? "—"}
                    </td>
                    <td className="py-2 text-right">
                      <button
                        onClick={() => handleDelete(d.id)}
                        className="text-xs text-red-400 hover:text-red-600"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
