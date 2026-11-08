import { useEffect, useState } from "react";
import { apiErrorMessage, buy, getHoldings, getQuote, getSummary, sell, type Holding } from "../api/client";
import Modal from "./Modal";

interface Props {
  action: "buy" | "sell";
  symbol: string;
  hint?: string;
  onClose: () => void;
  onDone: (message: string) => void;
}

// Two stages on purpose: the review stage exists to show a freshly quoted price,
// its as-of time, the estimated cost and the cash/position impact before submission.
// The preview is never authoritative — the server re-quotes and re-checks balances.
export default function PaperTradeDialog({ action, symbol: initialSymbol, hint, onClose, onDone }: Props) {
  const [stage, setStage] = useState<"entry" | "review">("entry");
  const [symbol, setSymbol] = useState(initialSymbol);
  const [sharesText, setSharesText] = useState("");
  const [cash, setCash] = useState<number | null>(null);
  const [holdings, setHoldings] = useState<Holding[] | null>(null);
  const [contextError, setContextError] = useState("");
  const [quote, setQuote] = useState<{ price: number; at: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getSummary(), getHoldings()])
      .then(([summary, rows]) => {
        setCash(summary.cash_balance);
        setHoldings(rows);
      })
      .catch(() =>
        setContextError("Cash and position balances are unavailable — the server still validates the order on submission."),
      );
  }, []);

  const ticker = symbol.trim().toUpperCase();
  const shares = Number(sharesText);
  const held = holdings?.find((h) => h.symbol === ticker)?.shares ?? null;
  const estimate = quote ? quote.price * shares : null;
  const cashAfter =
    estimate == null || cash == null ? null : action === "buy" ? cash - estimate : cash + estimate;
  const heldAfter = held == null ? null : held + (action === "sell" ? -shares : shares);

  const formatMoney = (v: number) =>
    `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const goToReview = async () => {
    if (!ticker) return setError("Enter a symbol.");
    if (!Number.isFinite(shares) || shares <= 0) return setError("Enter a quantity greater than zero.");

    setBusy(true);
    setError("");
    try {
      const q = await getQuote(ticker);
      if (typeof q?.price !== "number") throw new Error("no price returned");
      setQuote({ price: q.price, at: new Date().toLocaleTimeString() });
    } catch {
      setQuote(null);
      setError("Could not fetch a price for this symbol. You can still submit — the server re-quotes.");
    } finally {
      setStage("review");
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      if (action === "buy") await buy(ticker, shares);
      else await sell(ticker, shares);
      onDone(`${action === "buy" ? "Bought" : "Sold"} ${shares} share${shares === 1 ? "" : "s"} of ${ticker} (paper)`);
    } catch (err) {
      setError(apiErrorMessage(err));
      setBusy(false);
    }
  };

  return (
    <Modal title={`${action === "buy" ? "Buy" : "Sell"} — review paper trade`} onClose={onClose}>
      <p className="text-xs text-gray-500">Paper portfolio. No real orders are placed.</p>

      {stage === "entry" ? (
        <div className="space-y-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="trade-symbol" className="text-xs font-medium text-gray-500">
              Symbol
            </label>
            <input
              id="trade-symbol"
              className="border rounded px-3 py-1.5 text-sm uppercase"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="AAPL"
              autoComplete="off"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="trade-shares" className="text-xs font-medium text-gray-500">
              Shares
            </label>
            <input
              id="trade-shares"
              className="border rounded px-3 py-1.5 text-sm"
              type="number"
              min="0"
              step="any"
              value={sharesText}
              onChange={(e) => setSharesText(e.target.value)}
            />
            {hint && <p className="text-xs text-gray-400">{hint}</p>}
          </div>
        </div>
      ) : (
        <dl className="space-y-2 text-sm">
          <Row label="Action" value={action === "buy" ? "Buy" : "Sell"} />
          <Row label="Symbol" value={ticker} />
          <Row label="Quantity" value={`${shares} shares`} />
          <Row
            label="Price"
            value={quote ? `${formatMoney(quote.price)} as of ${quote.at}` : "Unavailable"}
          />
          <Row
            label={action === "buy" ? "Estimated cost" : "Estimated proceeds"}
            value={estimate == null ? "Unavailable" : formatMoney(estimate)}
          />
          <Row
            label="Cash"
            value={
              cash == null || cashAfter == null
                ? "Unavailable"
                : `${formatMoney(cash)} → about ${formatMoney(cashAfter)}`
            }
          />
          <Row
            label="Position"
            value={
              held == null
                ? "Unavailable"
                : `${held} → ${heldAfter} shares`
            }
          />
        </dl>
      )}

      {stage === "review" && (
        <p className="text-xs text-gray-400">
          These figures are a preview, not a reserved price. The server re-quotes and re-checks
          cash and positions when you confirm.
        </p>
      )}
      {contextError && <p className="text-xs text-amber-600">{contextError}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex justify-end gap-2 pt-2">
        {stage === "entry" ? (
          <>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={goToReview}
              disabled={busy}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? "Quoting…" : "Review paper trade"}
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => setStage("entry")}
              className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-50"
            >
              Back
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {busy ? "Submitting…" : "Confirm paper trade"}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-gray-500">{label}</dt>
      <dd className="font-medium text-gray-900 text-right">{value}</dd>
    </div>
  );
}
