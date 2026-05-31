import { useEffect, useState } from "react";
import { getSummary } from "../api/client";

interface Summary {
  cash_balance: number;
  equity_value: number;
  total_value: number;
  initial_deposit: number;
  pnl: number;
  pnl_pct: number;
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getSummary()
      .then(setSummary)
      .catch(() => setError("Failed to load portfolio summary"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-center mt-10 text-gray-500">Loading…</p>;
  if (error) return <p className="text-center mt-10 text-red-500">{error}</p>;
  if (!summary) return null;

  const pnlColor = summary.pnl >= 0 ? "text-green-600" : "text-red-600";

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <Card label="Total Value" value={`$${summary.total_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <Card label="Cash Balance" value={`$${summary.cash_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <Card label="Equity Value" value={`$${summary.equity_value.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <Card label="Initial Deposit" value={`$${summary.initial_deposit.toLocaleString("en-US", { minimumFractionDigits: 2 })}`} />
        <Card
          label="P&L"
          value={`${summary.pnl >= 0 ? "+" : ""}$${summary.pnl.toLocaleString("en-US", { minimumFractionDigits: 2 })}`}
          valueClass={pnlColor}
        />
        <Card
          label="P&L %"
          value={`${summary.pnl_pct >= 0 ? "+" : ""}${summary.pnl_pct.toFixed(2)}%`}
          valueClass={pnlColor}
        />
      </div>
    </div>
  );
}

function Card({ label, value, valueClass = "text-gray-900" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="bg-white rounded-xl shadow p-5 flex flex-col gap-1">
      <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</span>
      <span className={`text-2xl font-bold ${valueClass}`}>{value}</span>
    </div>
  );
}
