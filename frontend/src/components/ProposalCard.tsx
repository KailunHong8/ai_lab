import { useState } from "react";

interface AnalystReport {
  analyst: string;
  symbol: string;
  valuation_signal?: string;
  quality_signal?: string;
  catalyst?: string;
  key_risks?: string[];
  trend?: string;
  momentum?: string;
  rsi?: number;
  macd_signal?: string;
  key_levels?: Record<string, number>;
  news_tone?: string;
  top_themes?: string[];
  sentiment_score?: number;
  macro_context?: string;
  summary: string;
  data_sources: string[];
}

interface ResearchCase {
  side: string;
  symbol: string;
  thesis: string;
  supporting_points: string[];
  key_risk_acknowledged: string;
  confidence: string;
}

interface RiskFlag {
  code: string;
  severity: string;
  message: string;
}

interface RiskResult {
  approved: boolean;
  flags: RiskFlag[];
  commentary: string;
}

interface TraderDecision {
  action: string;
  confidence: string;
  rationale: string;
  suggested_size_pct: number;
  time_horizon: string;
}

export interface Proposal {
  proposal_id: string;
  symbol: string;
  analysis_date: string;
  fundamentals_report: AnalystReport;
  technical_report: AnalystReport;
  sentiment_report: AnalystReport;
  bull_case: ResearchCase;
  bear_case: ResearchCase;
  trader_decision: TraderDecision;
  risk_result: RiskResult;
}

const ACTION_COLORS: Record<string, string> = {
  BUY: "bg-emerald-100 text-emerald-800 border-emerald-300",
  SELL: "bg-red-100 text-red-800 border-red-300",
  HOLD: "bg-yellow-100 text-yellow-800 border-yellow-300",
};

const CONFIDENCE_DOTS: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 };

function Section({ title, children, defaultOpen = false }: {
  title: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-50 hover:bg-gray-100 text-sm font-medium text-left"
        onClick={() => setOpen((v) => !v)}
      >
        {title}
        <span className="text-gray-400">{open ? "▲" : "▼"}</span>
      </button>
      {open && <div className="px-4 py-3 text-sm space-y-2">{children}</div>}
    </div>
  );
}

function SourcesBadge({ sources }: { sources: string[] }) {
  return (
    <div className="flex gap-1 flex-wrap mt-1">
      {sources.map((s) => (
        <span key={s} className="text-xs bg-blue-50 text-blue-600 rounded px-1.5 py-0.5 font-mono">{s}</span>
      ))}
    </div>
  );
}

export default function ProposalCard({
  proposal,
  onAddToPortfolio,
  onDismiss,
}: {
  proposal: Proposal;
  onAddToPortfolio?: (action: string, symbol: string, sizePct: number) => void;
  onDismiss?: () => void;
}) {
  const { trader_decision: td, risk_result: rr } = proposal;
  const dots = CONFIDENCE_DOTS[td.confidence] ?? 2;

  return (
    <div className="bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b bg-gray-50">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold text-gray-900">{proposal.symbol}</span>
          <span className="text-xs text-gray-500">{proposal.analysis_date}</span>
          <span className={`border rounded-full px-3 py-0.5 text-sm font-semibold ${ACTION_COLORS[td.action] ?? ""}`}>
            {td.action}
          </span>
          <span className="text-xs text-gray-500">
            Confidence: {"●".repeat(dots)}{"○".repeat(3 - dots)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${rr.approved ? "text-emerald-600" : "text-red-600"}`}>
            {rr.approved ? "✓ Risk Approved" : "✗ Risk Blocked"}
          </span>
          {onDismiss && (
            <button onClick={onDismiss} className="text-gray-400 hover:text-gray-600 text-lg leading-none">×</button>
          )}
        </div>
      </div>

      {/* Trader rationale */}
      <div className="px-5 py-3 border-b bg-white">
        <p className="text-sm text-gray-700">{td.rationale}</p>
        {td.action === "BUY" && (
          <p className="text-xs text-gray-500 mt-1">
            Suggested size: {td.suggested_size_pct.toFixed(1)}% of portfolio · Horizon: {td.time_horizon}
          </p>
        )}
      </div>

      {/* Collapsible sections */}
      <div className="px-5 py-4 space-y-2">
        <Section title="Fundamentals" defaultOpen>
          <p>{proposal.fundamentals_report.summary}</p>
          <div className="flex gap-4 text-xs text-gray-500 mt-1">
            {proposal.fundamentals_report.valuation_signal && (
              <span>Valuation: <b>{proposal.fundamentals_report.valuation_signal}</b></span>
            )}
            {proposal.fundamentals_report.quality_signal && (
              <span>Quality: <b>{proposal.fundamentals_report.quality_signal}</b></span>
            )}
          </div>
          {proposal.fundamentals_report.catalyst && (
            <p className="text-xs text-emerald-700 mt-1">Catalyst: {proposal.fundamentals_report.catalyst}</p>
          )}
          <SourcesBadge sources={proposal.fundamentals_report.data_sources} />
        </Section>

        <Section title="Technical">
          <p>{proposal.technical_report.summary}</p>
          <div className="flex gap-4 text-xs text-gray-500 mt-1">
            {proposal.technical_report.trend && (
              <span>Trend: <b>{proposal.technical_report.trend}</b></span>
            )}
            {proposal.technical_report.rsi != null && (
              <span>RSI: <b>{proposal.technical_report.rsi.toFixed(1)}</b></span>
            )}
            {proposal.technical_report.macd_signal && (
              <span>MACD: <b>{proposal.technical_report.macd_signal}</b></span>
            )}
          </div>
          <SourcesBadge sources={proposal.technical_report.data_sources} />
        </Section>

        <Section title="Sentiment &amp; Macro">
          <p>{proposal.sentiment_report.summary}</p>
          {proposal.sentiment_report.macro_context && (
            <p className="text-xs text-gray-600 mt-1 italic">{proposal.sentiment_report.macro_context}</p>
          )}
          {proposal.sentiment_report.top_themes && proposal.sentiment_report.top_themes.length > 0 && (
            <div className="flex gap-1 flex-wrap mt-1">
              {proposal.sentiment_report.top_themes.map((t) => (
                <span key={t} className="text-xs bg-gray-100 text-gray-600 rounded px-1.5 py-0.5">{t}</span>
              ))}
            </div>
          )}
          <SourcesBadge sources={proposal.sentiment_report.data_sources} />
        </Section>

        <Section title="Bull Case">
          <p className="font-medium text-emerald-700">{proposal.bull_case.thesis}</p>
          <ul className="list-disc pl-4 space-y-0.5 mt-1">
            {proposal.bull_case.supporting_points.map((p, i) => (
              <li key={i} className="text-gray-700">{p}</li>
            ))}
          </ul>
          {proposal.bull_case.key_risk_acknowledged && (
            <p className="text-xs text-gray-500 mt-1 italic">Risk acknowledged: {proposal.bull_case.key_risk_acknowledged}</p>
          )}
        </Section>

        <Section title="Bear Case">
          <p className="font-medium text-red-700">{proposal.bear_case.thesis}</p>
          <ul className="list-disc pl-4 space-y-0.5 mt-1">
            {proposal.bear_case.supporting_points.map((p, i) => (
              <li key={i} className="text-gray-700">{p}</li>
            ))}
          </ul>
          {proposal.bear_case.key_risk_acknowledged && (
            <p className="text-xs text-gray-500 mt-1 italic">Risk acknowledged: {proposal.bear_case.key_risk_acknowledged}</p>
          )}
        </Section>

        <Section title="Risk Assessment">
          <p className="text-gray-700">{rr.commentary}</p>
          {rr.flags.length > 0 && (
            <ul className="mt-2 space-y-1">
              {rr.flags.map((f, i) => (
                <li key={i} className={`text-xs px-2 py-1 rounded ${f.severity === "block" ? "bg-red-50 text-red-700" : "bg-yellow-50 text-yellow-700"}`}>
                  [{f.severity.toUpperCase()}] {f.code}: {f.message}
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {/* Actions */}
      {(onAddToPortfolio || onDismiss) && (
        <div className="px-5 py-3 border-t bg-gray-50 flex gap-2 justify-end">
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="px-4 py-1.5 text-sm border rounded-lg text-gray-600 hover:bg-gray-100"
            >
              Dismiss
            </button>
          )}
          {onAddToPortfolio && rr.approved && td.action !== "HOLD" && (
            <button
              onClick={() => onAddToPortfolio(td.action, proposal.symbol, td.suggested_size_pct)}
              className="px-4 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            >
              Add to Portfolio →
            </button>
          )}
        </div>
      )}
    </div>
  );
}
