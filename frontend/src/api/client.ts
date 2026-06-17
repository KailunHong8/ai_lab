import axios from "axios";

const api = axios.create({ baseURL: "http://localhost:8000" });

// ── Market ────────────────────────────────────────────────────────────────────
export const getQuote = (symbol: string) =>
  api.get(`/api/market/quote/${symbol}`).then((r) => r.data);

export const getProfile = (symbol: string) =>
  api.get(`/api/market/profile/${symbol}`).then((r) => r.data);

export const searchSymbol = (q: string) =>
  api.get("/api/market/search", { params: { q } }).then((r) => r.data);

export const getHistory = (symbol: string, from: string, to: string) =>
  api.get(`/api/market/history/${symbol}`, { params: { from_date: from, to_date: to } }).then((r) => r.data);

// ── Portfolio ─────────────────────────────────────────────────────────────────
export const getSummary = () =>
  api.get("/api/portfolio/summary").then((r) => r.data);

export const getHoldings = () =>
  api.get("/api/portfolio/holdings").then((r) => r.data);

export const getTransactions = (params?: { symbol?: string; from_date?: string; to_date?: string }) =>
  api.get("/api/portfolio/transactions", { params }).then((r) => r.data);

export const deposit = (amount: number) =>
  api.post("/api/portfolio/deposit", { amount }).then((r) => r.data);

export const withdraw = (amount: number) =>
  api.post("/api/portfolio/withdraw", { amount }).then((r) => r.data);

export const buy = (symbol: string, shares: number) =>
  api.post("/api/portfolio/buy", { symbol, shares }).then((r) => r.data);

export const sell = (symbol: string, shares: number) =>
  api.post("/api/portfolio/sell", { symbol, shares }).then((r) => r.data);

// ── Agent ─────────────────────────────────────────────────────────────────────
export const agentChat = (
  message: string,
  session_id: string,
  provider = "bedrock",
  model?: string,
  signal?: AbortSignal,
  agent_mode = "auto",
) =>
  api
    .post("/api/agent/chat", { message, session_id, provider, model: model || null, agent_mode }, { signal })
    .then((r) => r.data);

// ── Sessions ──────────────────────────────────────────────────────────────────
export const listSessions = () =>
  api.get("/api/sessions").then((r) => r.data);

export const createSession = (name?: string, provider = "bedrock", model?: string) =>
  api.post("/api/sessions", { name, provider, model }).then((r) => r.data);

export const getSessionMessages = (session_id: string) =>
  api.get(`/api/sessions/${session_id}/messages`).then((r) => r.data);

export const renameSession = (session_id: string, name: string) =>
  api.patch(`/api/sessions/${session_id}/name`, { name }).then((r) => r.data);

export const deleteSession = (session_id: string) =>
  api.delete(`/api/sessions/${session_id}`).then((r) => r.data);

// ── Knowledge ─────────────────────────────────────────────────────────────────
export const uploadDocument = (formData: FormData) =>
  api.post("/api/knowledge/upload", formData).then((r) => r.data);

export const listDocuments = () =>
  api.get("/api/knowledge/documents").then((r) => r.data);

export const deleteDocument = (id: string) =>
  api.delete(`/api/knowledge/documents/${id}`).then((r) => r.data);

// ── Screener ──────────────────────────────────────────────────────────────────
export const runScreener = (tickers: string, minCriteria = 4) =>
  api
    .get("/api/screener/run", { params: { tickers, min_criteria: minCriteria } })
    .then((r) => r.data);

export const listOllamaModels = () =>
  api.get("/api/screener/models").then((r) => r.data);

// ── Simulation ────────────────────────────────────────────────────────────────
export const runSimulation = (payload: {
  strategy_description: string;
  symbol: string;
  benchmark_symbol?: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  provider?: string;
  model?: string;
  run_monte_carlo?: boolean;
  monte_carlo_sims?: number;
  run_walk_forward?: boolean;
  run_stress_tests?: boolean;
}) => api.post("/api/simulation/run", payload).then((r) => r.data);

export const runPortfolioSimulation = (payload: {
  strategy_description: string;
  holdings: { ticker: string; weight: number }[];
  benchmark_symbol?: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  provider?: string;
  model?: string;
  run_monte_carlo?: boolean;
  monte_carlo_sims?: number;
  run_walk_forward?: boolean;
  run_stress_tests?: boolean;
}) => api.post("/api/simulation/run-portfolio", payload).then((r) => r.data);
