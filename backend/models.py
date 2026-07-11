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
