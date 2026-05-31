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
export const agentChat = (message: string, session_id = "default") =>
  api.post("/api/agent/chat", { message, session_id }).then((r) => r.data);

export const clearSession = (session_id: string) =>
  api.delete(`/api/agent/chat/${session_id}`).then((r) => r.data);

// ── Simulation ────────────────────────────────────────────────────────────────
export const runSimulation = (payload: {
  strategy_description: string;
  symbol: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
}) => api.post("/api/simulation/run", payload).then((r) => r.data);
