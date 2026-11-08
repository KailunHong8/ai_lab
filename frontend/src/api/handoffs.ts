// Typed handoffs between workspaces. Router state carries identifiers and selections
// only — the receiving workspace resolves them through the API, so refresh works.

export interface DecisionContext {
  provider?: string;
  model?: string;
  session_id?: string;
  thesis_ids?: string[];
  document_ids?: string[];
  strategy_text?: string;
  simulation_run_id?: string;
}

export interface PortfolioTradeHandoff {
  prefillAction: "BUY" | "SELL";
  prefillSymbol: string;
  prefillSizePct?: number;
  decisionContext?: DecisionContext;
}

export interface StrategyDraftHandoff {
  strategy: string;
  symbol?: string;
  start_date?: string;
  end_date?: string;
  benchmark?: string;
}

export function asPortfolioHandoff(state: unknown): PortfolioTradeHandoff | null {
  const value = state as Partial<PortfolioTradeHandoff> | null;
  const action = value?.prefillAction;
  if (action !== "BUY" && action !== "SELL") return null;
  return {
    prefillAction: action,
    prefillSymbol: (value?.prefillSymbol ?? "").toUpperCase(),
    prefillSizePct: value?.prefillSizePct,
    decisionContext: value?.decisionContext,
  };
}

export function asStrategyHandoff(state: unknown): StrategyDraftHandoff | null {
  const value = state as Partial<StrategyDraftHandoff> | null;
  if (!value?.strategy?.trim()) return null;
  return {
    strategy: value.strategy,
    symbol: value.symbol,
    start_date: value.start_date,
    end_date: value.end_date,
    benchmark: value.benchmark,
  };
}
