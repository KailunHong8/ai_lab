from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, Enum
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
