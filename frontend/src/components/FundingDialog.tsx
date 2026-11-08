import { useState } from "react";
import { apiErrorMessage, deposit, withdraw } from "../api/client";
import Modal from "./Modal";

// Funding is deliberately separate from paper trades: moving cash in and out is a
// different job from buying or selling an instrument.
export default function FundingDialog({
  action,
  onClose,
  onDone,
}: {
  action: "deposit" | "withdraw";
  onClose: () => void;
  onDone: (message: string) => void;
}) {
  const [amountText, setAmountText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const amount = Number(amountText);

  const submit = async () => {
    if (!Number.isFinite(amount) || amount <= 0) return setError("Enter an amount greater than zero.");
    setBusy(true);
    setError("");
    try {
      if (action === "deposit") await deposit(amount);
      else await withdraw(amount);
      onDone(`${action === "deposit" ? "Deposited" : "Withdrew"} $${amount.toFixed(2)} (paper cash)`);
    } catch (err) {
      setError(apiErrorMessage(err));
      setBusy(false);
    }
  };

  return (
    <Modal title={action === "deposit" ? "Deposit paper cash" : "Withdraw paper cash"} onClose={onClose}>
      <p className="text-xs text-gray-500">Paper cash only. No real money moves.</p>

      <div className="flex flex-col gap-1">
        <label htmlFor="funding-amount" className="text-xs font-medium text-gray-500">
          Amount ($)
        </label>
        <input
          id="funding-amount"
          className="border rounded px-3 py-1.5 text-sm"
          type="number"
          min="0"
          step="any"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
        />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onClose}
          className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={submit}
          disabled={busy}
          className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Submitting…" : action === "deposit" ? "Confirm deposit" : "Confirm withdrawal"}
        </button>
      </div>
    </Modal>
  );
}
