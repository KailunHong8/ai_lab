import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getTransactions, listDecisions, type DecisionRow, type TransactionRow } from "../api/client";

const TYPE_COLOR: Record<string, string> = {
  BUY: "text-blue-600",
  SELL: "text-purple-600",
  DEPOSIT: "text-green-600",
  WITHDRAW: "text-red-600",
};

export default function PortfolioActivity({ refreshToken }: { refreshToken: number }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [transactions, setTransactions] = useState<TransactionRow[] | null>(null);
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [decisionLookupFailed, setDecisionLookupFailed] = useState(false);
  const [error, setError] = useState("");

  const query = searchParams.toString();
  const symbolFilter = searchParams.get("symbol") ?? "";
  const fromFilter = searchParams.get("from_date") ?? "";
  const toFilter = searchParams.get("to_date") ?? "";

  // The URL is the source of truth for filters, so a shared or reloaded link keeps them.
  useEffect(() => {
    const params = new URLSearchParams(query);
    getTransactions({
      symbol: params.get("symbol") ?? undefined,
      from_date: params.get("from_date") ?? undefined,
      to_date: params.get("to_date") ?? undefined,
    })
      .then((rows) => {
        setTransactions(rows);
        setError("");
      })
      .catch(() => setError("Failed to load transactions."));

    listDecisions()
      .then((rows: DecisionRow[]) => {
        setDecisions(rows);
        setDecisionLookupFailed(false);
      })
      .catch(() => setDecisionLookupFailed(true));
  }, [query, refreshToken]);

  const applyFilters = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const next = new URLSearchParams();
    const symbol = String(data.get("symbol") ?? "").trim().toUpperCase();
    if (symbol) next.set("symbol", symbol);
    const from = String(data.get("from_date") ?? "");
    if (from) next.set("from_date", from);
    const to = String(data.get("to_date") ?? "");
    if (to) next.set("to_date", to);
    setSearchParams(next);
  };

  const decisionByTransaction = new Map<number, DecisionRow>();
  for (const d of decisions) {
    if (d.transaction_id != null) decisionByTransaction.set(d.transaction_id, d);
  }

  return (
    <div className="space-y-4">
      {/* key={query} resets the inputs whenever the URL changes (e.g. Back/Forward). */}
      <form
        key={query}
        onSubmit={applyFilters}
        className="bg-white rounded-xl shadow p-4 flex flex-wrap gap-3 items-end"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="activity-symbol" className="text-xs text-gray-500">Symbol</label>
          <input
            id="activity-symbol"
            name="symbol"
            className="border rounded px-2 py-1 text-sm w-24"
            placeholder="AAPL"
            defaultValue={symbolFilter}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="activity-from" className="text-xs text-gray-500">From</label>
          <input
            id="activity-from"
            name="from_date"
            type="date"
            className="border rounded px-2 py-1 text-sm"
            defaultValue={fromFilter}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label htmlFor="activity-to" className="text-xs text-gray-500">To</label>
          <input
            id="activity-to"
            name="to_date"
            type="date"
            className="border rounded px-2 py-1 text-sm"
            defaultValue={toFilter}
          />
        </div>
        <button type="submit" className="bg-blue-600 text-white rounded px-4 py-1 text-sm font-medium hover:bg-blue-700">
          Filter
        </button>
      </form>

      {error ? (
        <p className="text-red-600">{error}</p>
      ) : transactions === null ? (
        <p className="text-gray-500">Loading…</p>
      ) : transactions.length === 0 ? (
        <p className="text-gray-500">No transactions found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white rounded-xl shadow text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                {["Date", "Type", "Symbol", "Shares", "Price", "Amount", "Decision"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => {
                const decision = decisionByTransaction.get(t.id);
                const isTrade = t.type === "BUY" || t.type === "SELL";
                return (
                  <tr key={t.id} className="border-t hover:bg-gray-50">
                    <td className="px-4 py-3">{new Date(t.timestamp).toLocaleString()}</td>
                    <td className={`px-4 py-3 font-medium ${TYPE_COLOR[t.type] ?? ""}`}>{t.type}</td>
                    <td className="px-4 py-3">{t.symbol ?? "—"}</td>
                    <td className="px-4 py-3">{t.shares?.toFixed(4) ?? "—"}</td>
                    <td className="px-4 py-3">{t.price != null ? `$${t.price.toFixed(2)}` : "—"}</td>
                    <td className="px-4 py-3">${t.amount.toFixed(2)}</td>
                    <td className="px-4 py-3 text-xs">
                      {!isTrade ? (
                        "—"
                      ) : decision ? (
                        <span
                          className="text-emerald-700"
                          title={[decision.provider, decision.model].filter(Boolean).join(" · ")}
                        >
                          AI-assisted
                        </span>
                      ) : decisionLookupFailed ? (
                        <span className="text-gray-400" title="Decision history could not be loaded">—</span>
                      ) : (
                        <span className="text-gray-400" title="No recorded decision context for this trade">
                          No recorded context
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
