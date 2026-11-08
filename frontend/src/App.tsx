import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import AssistantContextProvider from "./assistant/AssistantContextProvider";
import Layout from "./components/Layout";
import LegacyRedirect from "./components/LegacyRedirect";
import Portfolio from "./pages/Portfolio";
import Research from "./pages/Research";
import Agent from "./pages/Agent";
import Simulation from "./pages/Simulation";
import StrategyStudio from "./pages/StrategyStudio";

export default function App() {
  return (
    <BrowserRouter>
      <AssistantContextProvider>
        <Layout>
          <Routes>
            {/* Portfolio is home */}
            <Route path="/" element={<Navigate to="/portfolio" replace />} />
            <Route path="/portfolio" element={<Portfolio view="overview" />} />
            <Route path="/portfolio/positions" element={<Portfolio view="positions" />} />
            <Route path="/portfolio/activity" element={<Portfolio view="activity" />} />
            <Route path="/holdings" element={<LegacyRedirect to="/portfolio/positions" />} />
            <Route path="/transactions" element={<LegacyRedirect to="/portfolio/activity" />} />

            {/* Research: library first, company and screener as local views */}
            <Route path="/research" element={<Navigate to="/research/library" replace />} />
            <Route path="/research/library" element={<Research view="library" />} />
            <Route path="/research/company" element={<Research view="company" />} />
            <Route path="/research/discover" element={<Research view="discover" />} />
            <Route path="/market" element={<LegacyRedirect to="/research/company" />} />
            <Route path="/screener" element={<LegacyRedirect to="/research/discover" />} />

            {/* Strategies */}
            <Route path="/strategies" element={<StrategyStudio />} />
            <Route path="/strategy-studio" element={<LegacyRedirect to="/strategies" />} />

            {/* Compatibility views kept during migration */}
            <Route path="/agent" element={<Agent />} />
            <Route path="/simulation" element={<Simulation />} />

            <Route path="*" element={<Navigate to="/portfolio" replace />} />
          </Routes>
        </Layout>
      </AssistantContextProvider>
    </BrowserRouter>
  );
}
