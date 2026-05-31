import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Holdings from "./pages/Holdings";
import Transactions from "./pages/Transactions";
import Market from "./pages/Market";
import Agent from "./pages/Agent";
import Simulation from "./pages/Simulation";

export default function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/holdings" element={<Holdings />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/market" element={<Market />} />
          <Route path="/agent" element={<Agent />} />
          <Route path="/simulation" element={<Simulation />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
