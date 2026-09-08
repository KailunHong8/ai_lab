"""Shared Pydantic types for the multi-agent trading pipeline."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class Quote(BaseModel):
    symbol: str
    name: str = ""
    price: float
    change_pct: float = 0.0
    volume: Optional[int] = None
    market_cap: Optional[float] = None
    open: Optional[float] = None
    day_high: Optional[float] = None
    day_low: Optional[float] = None


class CompanyProfile(BaseModel):
    symbol: str
    name: str = ""
    sector: str = ""
    industry: str = ""
    description: str = ""


class Fundamentals(BaseModel):
    symbol: str
    pe_ratio: Optional[float] = None
    eps: Optional[float] = None
    revenue_ttm: Optional[float] = None
    gross_margin: Optional[float] = None
    debt_equity: Optional[float] = None
    roe: Optional[float] = None
    earnings_surprise: Optional[float] = None
    next_earnings_date: Optional[str] = None
    income_trend: Optional[dict] = None
    balance_trend: Optional[dict] = None


class NewsItem(BaseModel):
    headline: str
    summary: str = ""
    url: str = ""
    source: str = ""
    published_at: str = ""


class SentimentScore(BaseModel):
    bullish_pct: float = 0.0
    bearish_pct: float = 0.0
    score: float = 0.0
    article_count: int = 0


class MacroSnapshot(BaseModel):
    fed_funds_rate: Optional[float] = None
    cpi_yoy: Optional[float] = None
    unemployment: Optional[float] = None
    yield_curve: Optional[float] = None
    vix: Optional[float] = None
    fed_funds_trend: int = 0    # +1 rising, -1 falling, 0 flat
    cpi_trend: int = 0
    yield_curve_trend: int = 0
    vix_trend: int = 0


class TechnicalSnapshot(BaseModel):
    rsi: Optional[float] = None
    macd_signal: str = "neutral"        # bullish_cross | bearish_cross | neutral
    price_vs_sma50: str = "above"       # above | below
    price_vs_sma200: str = "above"      # above | below
    bollinger_position: str = "middle"  # upper | middle | lower
    trend: str = "sideways"             # up | down | sideways
    momentum: str = "weak"              # strong | weak | diverging


class AnalystReport(BaseModel):
    analyst: str                         # fundamentals | technical | sentiment
    symbol: str
    # Fundamentals
    valuation_signal: Optional[str] = None   # cheap | fair | expensive
    quality_signal: Optional[str] = None     # strong | neutral | weak
    catalyst: Optional[str] = None
    key_risks: Optional[list[str]] = None
    # Technical
    trend: Optional[str] = None
    momentum: Optional[str] = None
    rsi: Optional[float] = None
    macd_signal: Optional[str] = None
    key_levels: Optional[dict] = None
    # Sentiment
    news_tone: Optional[str] = None          # positive | neutral | negative
    top_themes: Optional[list[str]] = None
    sentiment_score: Optional[float] = None
    macro_context: Optional[str] = None
    # Common
    summary: str = ""
    data_sources: list[str] = []


class ResearchCase(BaseModel):
    side: str                            # bull | bear
    symbol: str
    thesis: str
    supporting_points: list[str]
    key_risk_acknowledged: str = ""
    confidence: str = "MEDIUM"           # LOW | MEDIUM | HIGH


class TraderDecision(BaseModel):
    action: str                          # BUY | SELL | HOLD
    confidence: str = "MEDIUM"          # LOW | MEDIUM | HIGH
    rationale: str
    suggested_size_pct: float = 0.0
    time_horizon: str = "medium"        # short | medium | long


class RiskFlag(BaseModel):
    code: str
    severity: str                        # block | warn
    message: str


class RiskResult(BaseModel):
    approved: bool
    flags: list[RiskFlag]
    commentary: str


class PortfolioSnapshot(BaseModel):
    total_value: float
    cash: float
    cash_pct: float
    holdings: list[dict]  # [{symbol, shares, value, weight_pct, sector}]
    sector_weights: dict  # {sector: pct}


class TradeProposalResult(BaseModel):
    proposal_id: str
    symbol: str
    analysis_date: str
    fundamentals_report: AnalystReport
    technical_report: AnalystReport
    sentiment_report: AnalystReport
    bull_case: ResearchCase
    bear_case: ResearchCase
    trader_decision: TraderDecision
    risk_result: RiskResult
