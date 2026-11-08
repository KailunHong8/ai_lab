import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import WorkspaceTabs from "../components/WorkspaceTabs";
import PaperTradeDialog from "../components/PaperTradeDialog";
import FundingDialog from "../components/FundingDialog";
import PortfolioOverview from "./PortfolioOverview";
import PortfolioPositions from "./PortfolioPositions";
import PortfolioActivity from "./PortfolioActivity";

type View = "overview" | "positions" | "activity";

const TABS = [
  { to: "/portfolio", label: "Overview", end: true },
  { to: "/portfolio/positions", label: "Positions" },
  { to: "/portfolio/activity", label: "Activity" },
];

interface ProposalPrefill {
  prefillAction?: string;
  prefillSymbol?: string;
  prefillSizePct?: number;
}

type TradeRequest = { action: "buy" | "sell"; symbol: string; hint?: string };

// A proposal handoff arrives as router state. It seeds the review dialog only —
// nothing is submitted until the user confirms.
function prefillToTrade(state: unknown): TradeRequest | null {
  const prefill = state as ProposalPrefill | null;
  if (!prefill?.prefillAction) return null;
  return {
    action: prefill.prefillAction.toUpperCase() === "SELL" ? "sell" : "buy",
    symbol: prefill.prefillSymbol ?? "",
    hint: prefill.prefillSizePct
      ? `The proposal suggested about ${prefill.prefillSizePct.toFixed(1)}% of portfolio value — enter the quantity you want.`
      : undefined,
  };
}

export default function Portfolio({ view }: { view: View }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [refreshToken, setRefreshToken] = useState(0);
  const [flash, setFlash] = useState("");
  const [trade, setTrade] = useState<TradeRequest | null>(() => prefillToTrade(location.state));
  const [funding, setFunding] = useState<"deposit" | "withdraw" | null>(null);

  // Clear the consumed handoff so a refresh or Back navigation cannot reopen the dialog.
  useEffect(() => {
    if (location.state) navigate(location.pathname + location.search, { replace: true, state: null });
  }, [location, navigate]);

  const complete = (message: string) => {
    setTrade(null);
    setFunding(null);
    setFlash(message);
    setRefreshToken((t) => t + 1);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900">Portfolio</h1>
      <p className="mt-1 text-xs font-medium uppercase tracking-wide text-gray-500">Paper portfolio</p>

      <div className="mt-4">
        <WorkspaceTabs tabs={TABS} />
      </div>

      {flash && <p className="mb-4 rounded-lg bg-green-50 px-3 py-2 text-sm text-green-700">{flash}</p>}

      {view === "overview" && <PortfolioOverview refreshToken={refreshToken} />}
      {view === "positions" && (
        <PortfolioPositions
          refreshToken={refreshToken}
          onTrade={(action, symbol) => setTrade({ action, symbol })}
          onFunding={setFunding}
        />
      )}
      {view === "activity" && <PortfolioActivity refreshToken={refreshToken} />}

      {trade && <PaperTradeDialog action={trade.action} symbol={trade.symbol} hint={trade.hint} onClose={() => setTrade(null)} onDone={complete} />}
      {funding && <FundingDialog action={funding} onClose={() => setFunding(null)} onDone={complete} />}
    </div>
  );
}
