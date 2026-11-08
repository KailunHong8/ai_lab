import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { asPortfolioHandoff, type DecisionContext } from "../api/handoffs";
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

type TradeRequest = {
  action: "buy" | "sell";
  symbol: string;
  hint?: string;
  decisionContext?: DecisionContext;
};

// A proposal handoff arrives as router state. It seeds the review dialog only —
// nothing is submitted until the user confirms, and cancelling changes nothing.
function prefillToTrade(state: unknown): TradeRequest | null {
  const handoff = asPortfolioHandoff(state);
  if (!handoff) return null;
  return {
    action: handoff.prefillAction === "SELL" ? "sell" : "buy",
    symbol: handoff.prefillSymbol,
    hint: handoff.prefillSizePct
      ? `The proposal suggested about ${handoff.prefillSizePct.toFixed(1)}% of portfolio value — enter the quantity you want.`
      : undefined,
    decisionContext: handoff.decisionContext,
  };
}

export default function Portfolio({ view }: { view: View }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [refreshToken, setRefreshToken] = useState(0);
  const [flash, setFlash] = useState("");
  const [trade, setTrade] = useState<TradeRequest | null>(null);
  const [funding, setFunding] = useState<"deposit" | "withdraw" | null>(null);

  // Consume the handoff here (not in a state initializer) so it also works when the
  // proposal arrives while Portfolio is already open. Clearing the state afterwards
  // means a refresh or Back navigation cannot reopen the dialog.
  useEffect(() => {
    const handoff = prefillToTrade(location.state);
    // Router state is external input; adopting it into dialog state is the point.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (handoff) setTrade(handoff);
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

      {trade && (
        <PaperTradeDialog
          action={trade.action}
          symbol={trade.symbol}
          hint={trade.hint}
          decisionContext={trade.decisionContext}
          onClose={() => setTrade(null)}
          onDone={complete}
        />
      )}
      {funding && <FundingDialog action={funding} onClose={() => setFunding(null)} onDone={complete} />}
    </div>
  );
}
