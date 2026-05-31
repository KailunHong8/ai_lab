import { useEffect, useState } from "react";
import { getTransactions } from "../api/client";

interface Transaction {
  id: number;
  symbol: string | null;
  type: string;
  shares: number | null;
  price: number | null;
  amount: number;
  timestamp: string;
}

export default function Transactions() {
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState({ symbol: "", from_date: "", to_date: "" });

  const load = () => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (filter.symbol) params.symbol = filter.symbol;
    if (filter.from_date) params.from_date = filter.from_date;
    if (filter.to_date) params.to_date = filter.to_date;
    getTransactions(params)
      .then(setTxns)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const typeColor: Record<string, string> = {
    BUY: "text-blue-600",
    SELL: "text-purple-600",
    DEPOSIT: "text-green-600",
    WITHDRAW: "text-red-600",
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Transactions</h1>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Symbol</label>
          <input
            className="border rounded px-2 py-1 text-sm w-24"
            placeholder="AAPL"
            value={filter.symbol}
            onChange={(e) => setFilter({ ...filter, symbol: e.target.value.toUpperCase() })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">From</label>
          <input
            type="date"
            className="border rounded px-2 py-1 text-sm"
            value={filter.from_date}
            onChange={(e) => setFilter({ ...filter, from_date: e.target.value })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">To</label>
          <input
            type="date"
            className="border rounded px-2 py-1 text-sm"
            value={filter.to_date}
            onChange={(e) => setFilter({ ...filter, to_date: e.target.value })}
          />
        </div>
        <button
          onClick={load}
          className="bg-blue-600 text-white rounded px-4 py-1 text-sm font-medium hover:bg-blue-700"
        >
          Filter
        </button>
      </div>

      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : txns.length === 0 ? (
        <p className="text-gray-500">No transactions found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white rounded-xl shadow text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                {["Date", "Type", "Symbol", "Shares", "Price", "Amount"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {txns.map((t) => (
                <tr key={t.id} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3">{new Date(t.timestamp).toLocaleString()}</td>
                  <td className={`px-4 py-3 font-medium ${typeColor[t.type] ?? ""}`}>{t.type}</td>
                  <td className="px-4 py-3">{t.symbol ?? "—"}</td>
                  <td className="px-4 py-3">{t.shares?.toFixed(4) ?? "—"}</td>
                  <td className="px-4 py-3">{t.price != null ? `$${t.price.toFixed(2)}` : "—"}</td>
                  <td className="px-4 py-3">${t.amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
