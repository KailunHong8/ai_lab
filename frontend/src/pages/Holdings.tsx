import { useEffect, useState } from "react";
import { getHoldings, buy, sell, deposit, withdraw } from "../api/client";

interface Holding {
  symbol: string;
  shares: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealised_pnl: number;
}

export default function Holdings() {
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ action: "buy", symbol: "", shares: "", amount: "" });
  const [msg, setMsg] = useState("");

  const load = () => {
    setLoading(true);
    getHoldings()
      .then(setHoldings)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const handleTrade = async (e: React.FormEvent) => {
    e.preventDefault();
    setMsg("");
    try {
      if (form.action === "buy") {
        await buy(form.symbol, parseFloat(form.shares));
        setMsg(`Bought ${form.shares} shares of ${form.symbol}`);
      } else if (form.action === "sell") {
        await sell(form.symbol, parseFloat(form.shares));
        setMsg(`Sold ${form.shares} shares of ${form.symbol}`);
      } else if (form.action === "deposit") {
        await deposit(parseFloat(form.amount));
        setMsg(`Deposited $${form.amount}`);
      } else if (form.action === "withdraw") {
        await withdraw(parseFloat(form.amount));
        setMsg(`Withdrew $${form.amount}`);
      }
      load();
    } catch (err: any) {
      setMsg(`Error: ${err.response?.data?.detail ?? err.message}`);
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Holdings</h1>

      {/* Trade form */}
      <form onSubmit={handleTrade} className="bg-white rounded-xl shadow p-4 mb-6 flex flex-wrap gap-3 items-end">
        <div className="flex flex-col gap-1">
          <label className="text-xs text-gray-500">Action</label>
          <select
            className="border rounded px-2 py-1 text-sm"
            value={form.action}
            onChange={(e) => setForm({ ...form, action: e.target.value })}
          >
            <option value="buy">Buy</option>
            <option value="sell">Sell</option>
            <option value="deposit">Deposit</option>
            <option value="withdraw">Withdraw</option>
          </select>
        </div>
        {(form.action === "buy" || form.action === "sell") && (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Symbol</label>
              <input
                className="border rounded px-2 py-1 text-sm w-24"
                placeholder="AAPL"
                value={form.symbol}
                onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })}
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-gray-500">Shares</label>
              <input
                className="border rounded px-2 py-1 text-sm w-24"
                type="number"
                min="0"
                step="any"
                value={form.shares}
                onChange={(e) => setForm({ ...form, shares: e.target.value })}
              />
            </div>
          </>
        )}
        {(form.action === "deposit" || form.action === "withdraw") && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-gray-500">Amount ($)</label>
            <input
              className="border rounded px-2 py-1 text-sm w-32"
              type="number"
              min="0"
              step="any"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
          </div>
        )}
        <button type="submit" className="bg-blue-600 text-white rounded px-4 py-1 text-sm font-medium hover:bg-blue-700">
          Submit
        </button>
        {msg && <span className="text-sm text-gray-700">{msg}</span>}
      </form>

      {/* Holdings table */}
      {loading ? (
        <p className="text-gray-500">Loading…</p>
      ) : holdings.length === 0 ? (
        <p className="text-gray-500">No open positions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white rounded-xl shadow text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                {["Symbol", "Shares", "Avg Cost", "Current Price", "Market Value", "Unrealised P&L"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => (
                <tr key={h.symbol} className="border-t hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{h.symbol}</td>
                  <td className="px-4 py-3">{h.shares.toFixed(4)}</td>
                  <td className="px-4 py-3">${h.avg_cost.toFixed(2)}</td>
                  <td className="px-4 py-3">${h.current_price.toFixed(2)}</td>
                  <td className="px-4 py-3">${h.market_value.toFixed(2)}</td>
                  <td className={`px-4 py-3 font-medium ${h.unrealised_pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
                    {h.unrealised_pnl >= 0 ? "+" : ""}${h.unrealised_pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
