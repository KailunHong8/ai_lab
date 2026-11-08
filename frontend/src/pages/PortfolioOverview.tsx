import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHoldings, getSummary, getTransactions, type Holding, type PortfolioSummary, type TransactionRow } from "../api/client";

export default function PortfolioOverview({ refreshToken }: { refreshToken: number }) {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [transactions, setTransactions] = useState<TransactionRow[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getSummary(), getHoldings(), getTransactions()])
      .then(([s, h, t]) => {
        setSummary(s);
        setHoldings(h);
        setTransactions(t);
        setError("");
      })
      .catch(() => setError("Failed to load portfolio data."));
  }, [refreshToken]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!summary) return <p className="text-gray-500">Loading…</p>;

  const pnlColor = summary.pnl >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card label="Total Value" value={money(summary.total_value)} />
        <Card label="Cash Balance" value={money(summary.cash_balance)} />
        <Card label="Equity Value" value={money(summary.equity_value)} />
        <Card
          label="P&L"
          value={`${summary.pnl >= 0 ? "+" : "-"}${money(Math.abs(summary.pnl))}`}
          valueClass={pnlColor}
        />
        <Card
          label="P&L %"
          value={`${summary.pnl_pct >= 0 ? "+" : ""}${summary.pnl_pct.toFixed(2)}%`}
          valueClass={pnlColor}
        />
        <Card label="Initial Deposit" value={money(summary.initial_deposit)} />
      </div>

      <Panel title="Positions" action={{ to: "/portfolio/positions", label: "View all positions" }}>
        {holdings.length === 0 ? (
          <p className="text-sm text-gray-500">
            No open positions yet. <Link className="text-blue-600 hover:underline" to="/portfolio/positions">Review a paper trade</Link>.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-gray-500">
                  <th className="pb-2 font-medium">Symbol</th>
                  <th className="pb-2 font-medium">Shares</th>
                  <th className="pb-2 font-medium">Market Value</th>
                  <th className="pb-2 font-medium">Unrealised P&L</th>
                </tr>
              </thead>
              <tbody>
                {holdings.slice(0, 5).map((h) => (
                  <tr key={h.symbol} className="border-b last:border-0">
                    <td className="py-2 font-medium">{h.symbol}</td>
                    <td className="py-2">{h.shares.toFixed(4)}</td>
                    <td className="py-2">{money(h.market_value)}</td>
                    <td className={`py-2 font-medium ${h.unrealised_pnl >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {h.unrealised_pnl >= 0 ? "+" : "-"}{money(Math.abs(h.unrealised_pnl))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Recent activity" action={{ to: "/portfolio/activity", label: "View all activity" }}>
        {transactions.length === 0 ? (
          <p className="text-sm text-gray-500">No transactions yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-gray-500">
                  <th className="pb-2 font-medium">Date</th>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 font-medium">Symbol</th>
                  <th className="pb-2 font-medium">Amount</th>
                </tr>
              </thead>
              <tbody>
                {transactions.slice(0, 5).map((t) => (
                  <tr key={t.id} className="border-b last:border-0">
                    <td className="py-2 text-gray-500">{new Date(t.timestamp).toLocaleString()}</td>
                    <td className="py-2 font-medium">{t.type}</td>
                    <td className="py-2">{t.symbol ?? "—"}</td>
                    <td className="py-2">{money(t.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

function money(v: number) {
  return `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function Card({ label, value, valueClass = "text-gray-900" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="bg-white rounded-xl shadow p-5 flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      <span className={`text-2xl font-bold ${valueClass}`}>{value}</span>
    </div>
  );
}

function Panel({
  title,
  action,
  children,
}: {
  title: string;
  action: { to: string; label: string };
  children: React.ReactNode;
}) {
  return (
    <section className="bg-white rounded-xl shadow p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="font-semibold text-gray-900">{title}</h2>
        <Link to={action.to} className="text-xs text-blue-600 hover:underline">
          {action.label} →
        </Link>
      </div>
      {children}
    </section>
  );
}
