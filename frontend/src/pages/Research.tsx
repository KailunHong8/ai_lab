import { useEffect, useRef, useState } from "react";
import { uploadDocument, listDocuments, deleteDocument, listOllamaModels } from "../api/client";

interface Doc {
  id: string;
  title: string;
  source: string;
  date: string | null;
  processed: boolean;
}

const BEDROCK_MODELS = ["eu.anthropic.claude-sonnet-4-6", "eu.anthropic.claude-haiku-4-5"];

export default function Research() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("ARK");
  const [date, setDate] = useState("");
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"file" | "text">("file");
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [provider, setProvider] = useState<"bedrock" | "ollama">("bedrock");
  const [model, setModel] = useState<string>(BEDROCK_MODELS[0]);
  const [ollamaModels, setOllamaModels] = useState<string[]>(["qwen2.5:9b"]);
  const [ollamaAvailable, setOllamaAvailable] = useState(false);

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

  const handleProviderChange = (p: "bedrock" | "ollama") => {
    setProvider(p);
    if (p === "bedrock") setModel(BEDROCK_MODELS[0]);
    else setModel(ollamaModels[0] || "qwen2.5:9b");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return setStatus("Title is required.");

    const fd = new FormData();
    fd.append("title", title.trim());
    fd.append("source", source.trim() || "ARK");
    if (date) fd.append("date", date);
    fd.append("provider", provider);
    fd.append("model", model);

    if (tab === "file") {
      const file = fileRef.current?.files?.[0];
      if (!file) return setStatus("Select a file.");
      fd.append("file", file);
    } else {
      if (!text.trim()) return setStatus("Paste some text.");
      fd.append("text", text.trim());
    }

    setLoading(true);
    setStatus(null);
    try {
      const res = await uploadDocument(fd);
      if (res.status === "duplicate") {
        setStatus("Already in knowledge base.");
      } else if (res.imported !== undefined) {
        const msg =
          res.imported === 0
            ? `All ${res.duplicates} emails already in library.`
            : `Imported ${res.imported} email${res.imported !== 1 ? "s" : ""}${
                res.duplicates ? ` (${res.duplicates} duplicates skipped)` : ""
              }. Thesis extraction running in background.`;
        setStatus(msg);
        setTitle("");
        setDate("");
        if (fileRef.current) fileRef.current.value = "";
        await load();
      } else {
        setStatus("Added successfully.");
        setTitle("");
        setDate("");
        setText("");
        if (fileRef.current) fileRef.current.value = "";
        await load();
      }
    } catch (err: any) {
      setStatus(`Error: ${err.response?.data?.detail ?? err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    await deleteDocument(id);
    setDocs((prev) => prev.filter((d) => d.id !== id));
  };

  const modelOptions = provider === "bedrock" ? BEDROCK_MODELS : ollamaModels;

  return (
    <div className="space-y-8">
      <h1 className="text-2xl font-bold">Research Library</h1>

      {/* Upload form */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="font-semibold text-lg mb-4">Add Article</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
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
              <label className="text-xs text-gray-500 block mb-1">Source</label>
              <input
                className="w-full border rounded px-3 py-1.5 text-sm"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="ARK"
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

          {/* Provider + model for extraction */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-xs text-gray-500">Extract with:</span>
            <div className="flex rounded border overflow-hidden">
              {(["bedrock", "ollama"] as const).map((p) => (
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
                  {p === "bedrock" ? "Bedrock" : `Ollama${!ollamaAvailable ? " (offline)" : ""}`}
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

          {/* Tab toggle */}
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
            <input
              ref={fileRef}
              type="file"
              accept=".txt,.md,.pdf,.mbox"
              className="text-sm"
            />
          ) : (
            <textarea
              className="w-full border rounded px-3 py-2 text-sm h-36 resize-y"
              placeholder="Paste the article content here…"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          )}

          {status && (
            <p className={`text-sm ${status.startsWith("Error") ? "text-red-500" : "text-green-600"}`}>
              {status}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 text-white rounded px-5 py-2 text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "Adding…" : "Add to library"}
          </button>
        </form>
      </div>

      {/* Document list */}
      <div className="bg-white rounded-xl shadow p-6">
        <h2 className="font-semibold text-lg mb-4">Library ({docs.length})</h2>
        {docs.length === 0 ? (
          <p className="text-sm text-gray-400">No articles yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b">
                <th className="pb-2 font-medium">Title</th>
                <th className="pb-2 font-medium">Source</th>
                <th className="pb-2 font-medium">Date</th>
                <th className="pb-2 font-medium">Processed</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-b last:border-0 hover:bg-gray-50">
                  <td className="py-2 pr-4 max-w-xs truncate">{d.title}</td>
                  <td className="py-2 pr-4 text-gray-500">{d.source}</td>
                  <td className="py-2 pr-4 text-gray-500">{d.date ?? "—"}</td>
                  <td className="py-2 pr-4">
                    {d.processed ? (
                      <span className="text-green-600">Yes</span>
                    ) : (
                      <span className="text-yellow-500">Pending</span>
                    )}
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
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
