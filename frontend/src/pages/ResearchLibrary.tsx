import { useEffect, useState } from "react";
import axios from "axios";
import { apiErrorMessage, deleteDocument, listDocuments } from "../api/client";
import AddSourceDialog from "../components/AddSourceDialog";

interface Doc {
  id: string;
  title: string;
  source: string;
  date: string | null;
  corpus: string | null;
  source_type: string | null;
  fund: string | null;
  recency_flag: string | null;
  reliability_tier: number | null;
  expiration_at: string | null;
}

const RECENCY_BADGE: Record<string, string> = {
  evergreen: "bg-green-100 text-green-700",
  timely: "bg-blue-100 text-blue-700",
  stale: "bg-gray-100 text-gray-500",
};

const CORPUS_LABEL: Record<string, string> = {
  principles: "Principles",
  market_opinion: "Market",
};

// Library first: saved evidence is the default view, and adding a source is one dialog.
export default function ResearchLibrary() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [corpus, setCorpus] = useState<"all" | "principles" | "market_opinion">("all");
  const [addOpen, setAddOpen] = useState(false);
  const [error, setError] = useState("");
  const [cleanupStatus, setCleanupStatus] = useState<string | null>(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);

  const load = () => {
    listDocuments()
      .then((rows: Doc[]) => {
        setDocs(rows);
        setError("");
      })
      .catch(() => setError("Failed to load the research library."));
  };

  useEffect(load, []);

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
      load();
    } catch (err) {
      setCleanupStatus(`Error: ${apiErrorMessage(err)}`);
    } finally {
      setCleanupLoading(false);
    }
  };

  const filtered = docs.filter((d) => corpus === "all" || d.corpus === corpus);
  const principlesCount = docs.filter((d) => d.corpus === "principles").length;
  const marketCount = docs.filter((d) => d.corpus === "market_opinion").length;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Research Library</h1>
          <p className="mt-1 text-sm text-gray-500">
            Saved evidence for research and recommendations. Expired sources stay visible and are
            excluded from retrieval.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setAddOpen(true)}
          className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          Add source
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <label htmlFor="library-corpus" className="text-xs text-gray-500">
          Corpus
        </label>
        <select
          id="library-corpus"
          className="border rounded px-2 py-1 text-sm bg-white"
          value={corpus}
          onChange={(e) => setCorpus(e.target.value as typeof corpus)}
        >
          <option value="all">All ({docs.length})</option>
          <option value="principles">Principles ({principlesCount})</option>
          <option value="market_opinion">Market opinion ({marketCount})</option>
        </select>
        <button
          type="button"
          onClick={handleCleanup}
          disabled={cleanupLoading}
          className="text-xs px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          {cleanupLoading ? "Cleaning…" : "Clean expired research"}
        </button>
        {cleanupStatus && (
          <span className={`text-xs ${cleanupStatus.startsWith("Error") ? "text-red-600" : "text-green-700"}`}>
            {cleanupStatus}
          </span>
        )}
      </div>

      {error && <p className="text-red-600">{error}</p>}

      {!error && filtered.length === 0 ? (
        <p className="text-sm text-gray-500">
          No sources yet. Use Add source to bring in a fund letter, article, or external research answer.
        </p>
      ) : (
        !error && (
          <div className="overflow-x-auto bg-white rounded-xl shadow">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-gray-500">
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Corpus</th>
                  <th className="px-4 py-3 font-medium">Source</th>
                  <th className="px-4 py-3 font-medium">Type / Tier</th>
                  <th className="px-4 py-3 font-medium">Freshness</th>
                  <th className="px-4 py-3 font-medium">Date / Expiry</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {filtered.map((d) => {
                  const expired = d.expiration_at ? new Date(d.expiration_at) <= new Date() : false;
                  return (
                    <tr key={d.id} className={`border-b last:border-0 hover:bg-gray-50 ${expired ? "opacity-60" : ""}`}>
                      <td className="px-4 py-3 max-w-xs truncate" title={d.title}>{d.title}</td>
                      <td className="px-4 py-3">
                        {d.corpus ? (
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                              d.corpus === "principles"
                                ? "bg-purple-100 text-purple-700"
                                : "bg-orange-100 text-orange-700"
                            }`}
                          >
                            {CORPUS_LABEL[d.corpus] ?? d.corpus}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3 text-gray-500">{d.fund || d.source}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">
                        {d.source_type ?? "—"}
                        {d.reliability_tier != null ? ` · tier ${d.reliability_tier}` : ""}
                      </td>
                      <td className="px-4 py-3">
                        {expired ? (
                          <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-red-100 text-red-600">expired</span>
                        ) : d.recency_flag ? (
                          <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${RECENCY_BADGE[d.recency_flag] ?? "bg-gray-100 text-gray-500"}`}>
                            {d.recency_flag}
                          </span>
                        ) : "—"}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-xs text-gray-500">
                        {d.date ?? "—"}
                        {d.expiration_at ? ` · exp ${d.expiration_at.slice(0, 10)}` : ""}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
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
          </div>
        )
      )}

      {addOpen && <AddSourceDialog onClose={() => setAddOpen(false)} onIngested={load} />}
    </div>
  );
}
