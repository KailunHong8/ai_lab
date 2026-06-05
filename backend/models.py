from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, Enum, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from backend.db import Base


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
    source: Mapped[str] = mapped_column(String(64))          # "ARK", "textbook", etc.
    title: Mapped[str] = mapped_column(String(256))
    content: Mapped[str] = mapped_column(Text)
    date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    email_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    processed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    theses: Mapped[list["Thesis"]] = relationship("Thesis", back_populates="document", cascade="all, delete-orphan")


class Thesis(Base):
    """Structured investment thesis extracted from a document by LLM."""
    __tablename__ = "theses"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(64))          # "ARK", "textbook", etc.
    theme: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    entity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    stance: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # bullish/bearish/neutral
    claims: Mapped[str] = mapped_column(Text)                # JSON array of strings
    type: Mapped[str] = mapped_column(String(16))            # "fact" or "forecast"
    date: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    document_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
