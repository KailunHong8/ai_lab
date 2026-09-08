from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, Enum, Text, Boolean, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.db import Base


# ── Knowledge taxonomy constants ──────────────────────────────────────────────

CORPUS_PRINCIPLES = "principles"
CORPUS_MARKET_OPINION = "market_opinion"

SOURCE_TYPE_PRINCIPLE_TEXT = "principle_text"
SOURCE_TYPE_FUND_LETTER = "fund_letter"
SOURCE_TYPE_WEB_RESEARCH = "web_research"
SOURCE_TYPE_USER_SYNTHESIS = "user_synthesis"

CHANNEL_MANUAL_PASTE = "manual_paste"
CHANNEL_FILE_UPLOAD = "file_upload"
CHANNEL_MBOX = "mbox"
CHANNEL_PERPLEXITY = "perplexity"
CHANNEL_CHATGPT = "chatgpt"

RECENCY_EVERGREEN = "evergreen"
RECENCY_TIMELY = "timely"
RECENCY_STALE = "stale"

RELIABILITY_PRINCIPLES = 1
RELIABILITY_FUND_LETTER = 2
RELIABILITY_USER_SYNTHESIS = 3
RELIABILITY_WEB_RESEARCH = 4


class TransactionType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, default="default")
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    initial_deposit: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)

    positions: Mapped[list["Position"]] = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    transactions: Mapped[list["Transaction"]] = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=0)

    user: Mapped["User"] = relationship("User", back_populates="positions")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=True)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship("User", back_populates="transactions")


# ── Knowledge Base ─────────────────────────────────────────────────────────────

class Document(Base):
    """Raw document archive — markdown from Gmail or manually added files."""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))          # fund name, e.g. "ARK", "GMO", etc.
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text)
    date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    email_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Taxonomy fields (spec §7)
    corpus: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)           # principles | market_opinion
    source_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)                  # principle_text | fund_letter | web_research | user_synthesis
    fund: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)             # ARK | GMO | Sequoia | Bridgewater | …
    channel: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)                      # manual_paste | file_upload | mbox | perplexity
    reliability_tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    published_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    recency_flag: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default=RECENCY_TIMELY)  # evergreen | timely | stale
    expiration_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)             # TTL for web_research entries
    citations_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                     # JSON list of citation URLs/titles
    ingestion_job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    theses: Mapped[list["Thesis"]] = relationship("Thesis", back_populates="document", cascade="all, delete-orphan")


class Thesis(Base):
    """Structured investment thesis extracted from a document by LLM."""
    __tablename__ = "theses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))          # fund name or "textbook"
    theme: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    entity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    stance: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # bullish/bearish/neutral
    claims: Mapped[str] = mapped_column(Text)                # JSON array of strings
    type: Mapped[str] = mapped_column(String(16))            # "fact" or "forecast"
    date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Taxonomy fields mirrored from parent document (spec §7)
    source_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    fund: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    reliability_tier: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recency_flag: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    expiration_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    document: Mapped[Optional["Document"]] = relationship("Document", back_populates="theses")


class Entity(Base):
    """Market entity (stock/ETF) with sector metadata."""
    __tablename__ = "entities"

    symbol: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    outgoing: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship", foreign_keys="EntityRelationship.from_symbol",
        back_populates="from_entity", cascade="all, delete-orphan"
    )
    incoming: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship", foreign_keys="EntityRelationship.to_symbol",
        back_populates="to_entity"
    )


class EntityRelationship(Base):
    """Directed relationship between two market entities."""
    __tablename__ = "entity_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("entities.symbol"), index=True)
    to_symbol: Mapped[str] = mapped_column(String(16), ForeignKey("entities.symbol"), index=True)
    rel_type: Mapped[str] = mapped_column(String(32))    # supplier/competitor/customer/partner
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    from_entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[from_symbol], back_populates="outgoing")
    to_entity: Mapped["Entity"] = relationship("Entity", foreign_keys=[to_symbol], back_populates="incoming")


# ── Screener ──────────────────────────────────────────────────────────────────

class ScreenerRun(Base):
    """One execution of the value screener — captures the input tickers and thresholds."""
    __tablename__ = "screener_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tickers: Mapped[str] = mapped_column(Text)           # raw comma-separated input
    min_criteria: Mapped[int] = mapped_column(Integer, default=4)
    passed_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    ran_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    results: Mapped[list["ScreenerResult"]] = relationship(
        "ScreenerResult", back_populates="run", cascade="all, delete-orphan"
    )


class ScreenerResult(Base):
    """Per-ticker result from one screener run."""
    __tablename__ = "screener_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("screener_runs.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    sector: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    passes_screen: Mapped[bool] = mapped_column(Boolean, default=False)
    criteria_passed: Mapped[int] = mapped_column(Integer, default=0)
    # raw fundamentals stored as JSON so the copilot can read them back
    fundamentals: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    run: Mapped["ScreenerRun"] = relationship("ScreenerRun", back_populates="results")


# ── Chat Sessions ─────────────────────────────────────────────────────────────

class ChatSession(Base):
    """Named copilot session — persists conversation history across page loads."""
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider: Mapped[str] = mapped_column(String(16), default="bedrock")
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # compressed older history
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session",
        order_by="ChatMessage.sequence",
        cascade="all, delete-orphan",
    )


class ChatMessage(Base):
    """One message turn in a chat session (Bedrock Converse format preserved as JSON)."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("chat_sessions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)        # ordering within session
    role: Mapped[str] = mapped_column(String(16))         # "user" or "assistant"
    content: Mapped[dict] = mapped_column(JSON)           # raw Bedrock content block list
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


# ── Simulation Runs ───────────────────────────────────────────────────────────

class SimulationRun(Base):
    """Immutable record of one simulation run — enough to reproduce and re-open."""
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)          # UUID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    mode: Mapped[str] = mapped_column(String(16))                           # "single" | "portfolio"
    strategy_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)           # single mode
    holdings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)          # portfolio: [{ticker, weight}]
    parsed_strategy_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # rules + warnings snapshot
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    benchmark_symbol: Mapped[str] = mapped_column(String(16))
    commission_bps: Mapped[float] = mapped_column(Float)
    slippage_bps: Mapped[float] = mapped_column(Float)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    request_json: Mapped[str] = mapped_column(Text)        # full request payload (reproduce run)
    summary_json: Mapped[str] = mapped_column(Text)        # scalar metrics for cheap listing
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # full payload incl. curves

    # Phase 2 — nullable FKs to Strategy Studio records
    strategy_version_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    data_snapshot_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    validation_report_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    decisions: Mapped[list["Decision"]] = relationship("Decision", back_populates="simulation_run")


# ── Strategy Studio ───────────────────────────────────────────────────────────

class Strategy(Base):
    """A named strategy — container for versioned StrategyDefinition records."""
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    versions: Mapped[list["StrategyVersion"]] = relationship("StrategyVersion", back_populates="strategy")


class StrategyVersion(Base):
    """
    Immutable once status != 'draft'.
    Editing a draft creates a new version.
    """
    __tablename__ = "strategy_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategies.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    definition_json: Mapped[str] = mapped_column(Text)
    definition_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")   # draft | reviewed | archived
    source_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parser_output_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_edits_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    compiled_plan_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    strategy: Mapped["Strategy"] = relationship("Strategy", back_populates="versions")
    validation_reports: Mapped[list["ValidationReport"]] = relationship("ValidationReport", back_populates="strategy_version")


class DataSnapshot(Base):
    """Immutable record of one data fetch — provider, symbols, date range, content hash."""
    __tablename__ = "data_snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbols_json: Mapped[str] = mapped_column(Text)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(32))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    manifest_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ValidationReport(Base):
    """Immutable validation report — folds, holdout, bootstrap, regime breakdown."""
    __tablename__ = "validation_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    strategy_version_id: Mapped[str] = mapped_column(String(64), ForeignKey("strategy_versions.id"), index=True)
    data_snapshot_id: Mapped[str] = mapped_column(String(64), ForeignKey("data_snapshots.id"))
    fold_results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    holdout_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bootstrap_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    regime_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary_json: Mapped[str] = mapped_column(Text)
    gate_results_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    strategy_version: Mapped["StrategyVersion"] = relationship("StrategyVersion", back_populates="validation_reports")
    data_snapshot: Mapped["DataSnapshot"] = relationship("DataSnapshot")


# ── Decision Ledger ───────────────────────────────────────────────────────────

class Decision(Base):
    """Auditable record of one AI-assisted paper-trading decision."""
    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)           # UUID
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[int] = mapped_column(Integer, default=1)
    action: Mapped[str] = mapped_column(String(8))                          # "BUY" | "SELL"
    symbol: Mapped[str] = mapped_column(String(16))
    shares: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("chat_sessions.id"), nullable=True)
    thesis_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # JSON list of Thesis.id
    document_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)   # JSON list of Document.id
    strategy_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    strategy_parsed_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    simulation_run_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("simulation_runs.id"), nullable=True)
    confirmed_by_user: Mapped[bool] = mapped_column(Boolean, default=False)

    simulation_run: Mapped[Optional["SimulationRun"]] = relationship("SimulationRun", back_populates="decisions")


# ── Multi-Agent Pipeline ───────────────────────────────────────────────────────

class DataCache(Base):
    """Key-value cache for market data with TTL."""
    __tablename__ = "data_cache"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    data: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class TradeProposal(Base):
    """Full record of one multi-agent analysis run."""
    __tablename__ = "trade_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    analysis_date: Mapped[str] = mapped_column(String(10))
    session_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("chat_sessions.id"), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Full JSON payload of the TradeProposalResult
    result_json: Mapped[str] = mapped_column(Text)
    # Quick-access fields
    action: Mapped[str] = mapped_column(String(8))           # BUY | SELL | HOLD
    confidence: Mapped[str] = mapped_column(String(8))
    risk_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    transaction_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("transactions.id"), nullable=True)


class DecisionMemory(Base):
    """Tracks prior trade proposals + realized returns for reflection."""
    __tablename__ = "decision_memory"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(8))
    decision_date: Mapped[str] = mapped_column(String(10))
    price_at_decision: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    proposal_id: Mapped[str] = mapped_column(String(64), ForeignKey("trade_proposals.id"))
    horizon_date: Mapped[str] = mapped_column(String(10))    # decision_date + 30 days
    realized_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    spy_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reflection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reflected_at: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
