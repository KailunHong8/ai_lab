import { useEffect, useState } from "react";
import { getHoldings, type Holding } from "../api/client";

export default function PortfolioPositions({
  refreshToken,
  onTrade,
  onFunding,
}: {
  refreshToken: number;
  onTrade: (action: "buy" | "sell", symbol: string) => void;
  onFunding: (action: "deposit" | "withdraw") => void;
}) {
  const [holdings, setHoldings] = useState<Holding[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getHoldings()
      .then((rows) => {
        setHoldings(rows);
        setError("");
      })
      .catch(() => setError("Failed to load positions."));
  }, [refreshToken]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onTrade("buy", "")}
          className="rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          Buy
        </button>
        <button
          type="button"
          onClick={() => onTrade("sell", "")}
          className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Sell
        </button>
        <span className="mx-1 hidden w-px self-stretch bg-gray-200 sm:block" />
        <button
          type="button"
          onClick={() => onFunding("deposit")}
          className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Deposit
        </button>
        <button
          type="button"
          onClick={() => onFunding("withdraw")}
          className="rounded-lg border border-gray-300 px-4 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
        >
          Withdraw
        </button>
      </div>

      {error && <p className="text-red-600">{error}</p>}
      {!error && holdings === null && <p className="text-gray-500">Loading…</p>}
      {holdings !== null && holdings.length === 0 && (
        <p className="text-gray-500">No open positions. Use Buy to open a paper position.</p>
      )}
      {holdings !== null && holdings.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full bg-white rounded-xl shadow text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
              <tr>
                {["Symbol", "Shares", "Avg Cost", "Current Price", "Market Value", "Unrealised P&L", ""].map((h) => (
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
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    <button type="button" onClick={() => onTrade("buy", h.symbol)} className="text-xs text-blue-600 hover:underline">
                      Buy
                    </button>
                    <button type="button" onClick={() => onTrade("sell", h.symbol)} className="ml-3 text-xs text-blue-600 hover:underline">
                      Sell
                    </button>
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
