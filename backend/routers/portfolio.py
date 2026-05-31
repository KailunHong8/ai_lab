from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Position, Transaction, TransactionType, User
from backend.services import fmp

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

DEFAULT_USER_ID = 1  # single-user v1


# ── helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == DEFAULT_USER_ID))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=DEFAULT_USER_ID, username="default", cash_balance=Decimal(0), initial_deposit=Decimal(0))
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _get_position(db: AsyncSession, symbol: str) -> Optional[Position]:
    result = await db.execute(
        select(Position).where(Position.user_id == DEFAULT_USER_ID, Position.symbol == symbol.upper())
    )
    return result.scalar_one_or_none()


# ── schemas ───────────────────────────────────────────────────────────────────

class DepositRequest(BaseModel):
    amount: float


class WithdrawRequest(BaseModel):
    amount: float


class BuyRequest(BaseModel):
    symbol: str
    shares: float


class SellRequest(BaseModel):
    symbol: str
    shares: float


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/deposit")
async def deposit(req: DepositRequest, db: AsyncSession = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(400, "Deposit amount must be positive")
    user = await _get_or_create_user(db)
    amount = Decimal(str(req.amount))
    user.cash_balance += amount
    user.initial_deposit += amount
    txn = Transaction(
        user_id=DEFAULT_USER_ID,
        type=TransactionType.DEPOSIT,
        amount=amount,
        timestamp=datetime.utcnow(),
    )
    db.add(txn)
    await db.commit()
    return {"cash_balance": float(user.cash_balance), "initial_deposit": float(user.initial_deposit)}


@router.post("/withdraw")
async def withdraw(req: WithdrawRequest, db: AsyncSession = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(400, "Withdrawal amount must be positive")
    user = await _get_or_create_user(db)
    amount = Decimal(str(req.amount))
    if amount > user.cash_balance:
        raise HTTPException(400, "Insufficient cash balance")
    user.cash_balance -= amount
    txn = Transaction(
        user_id=DEFAULT_USER_ID,
        type=TransactionType.WITHDRAW,
        amount=amount,
        timestamp=datetime.utcnow(),
    )
    db.add(txn)
    await db.commit()
    return {"cash_balance": float(user.cash_balance)}


@router.post("/buy")
async def buy(req: BuyRequest, db: AsyncSession = Depends(get_db)):
    if req.shares <= 0:
        raise HTTPException(400, "Shares must be positive")
    symbol = req.symbol.upper()
    quote = await fmp.get_quote(symbol)
    if not quote:
        raise HTTPException(404, f"Symbol {symbol} not found")
    price = Decimal(str(quote["price"]))
    shares = Decimal(str(req.shares))
    cost = price * shares

    user = await _get_or_create_user(db)
    if cost > user.cash_balance:
        raise HTTPException(400, f"Insufficient funds: need {float(cost):.2f}, have {float(user.cash_balance):.2f}")

    user.cash_balance -= cost
    position = await _get_position(db, symbol)
    if position is None:
        position = Position(user_id=DEFAULT_USER_ID, symbol=symbol, shares=shares, avg_cost=price)
        db.add(position)
    else:
        total_shares = position.shares + shares
        position.avg_cost = (position.avg_cost * position.shares + price * shares) / total_shares
        position.shares = total_shares

    txn = Transaction(
        user_id=DEFAULT_USER_ID,
        symbol=symbol,
        type=TransactionType.BUY,
        shares=shares,
        price=price,
        amount=cost,
        timestamp=datetime.utcnow(),
    )
    db.add(txn)
    await db.commit()
    return {
        "symbol": symbol,
        "shares": float(position.shares),
        "avg_cost": float(position.avg_cost),
        "cash_balance": float(user.cash_balance),
    }


@router.post("/sell")
async def sell(req: SellRequest, db: AsyncSession = Depends(get_db)):
    if req.shares <= 0:
        raise HTTPException(400, "Shares must be positive")
    symbol = req.symbol.upper()
    position = await _get_position(db, symbol)
    shares = Decimal(str(req.shares))

    if position is None or position.shares < shares:
        held = float(position.shares) if position else 0
        raise HTTPException(400, f"Insufficient shares: trying to sell {req.shares}, holding {held}")

    quote = await fmp.get_quote(symbol)
    if not quote:
        raise HTTPException(404, f"Symbol {symbol} not found")
    price = Decimal(str(quote["price"]))
    proceeds = price * shares

    user = await _get_or_create_user(db)
    user.cash_balance += proceeds
    position.shares -= shares
    if position.shares == 0:
        await db.delete(position)

    txn = Transaction(
        user_id=DEFAULT_USER_ID,
        symbol=symbol,
        type=TransactionType.SELL,
        shares=shares,
        price=price,
        amount=proceeds,
        timestamp=datetime.utcnow(),
    )
    db.add(txn)
    await db.commit()
    return {
        "symbol": symbol,
        "proceeds": float(proceeds),
        "cash_balance": float(user.cash_balance),
    }


@router.get("/holdings")
async def holdings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Position).where(Position.user_id == DEFAULT_USER_ID))
    positions = result.scalars().all()

    rows = []
    for pos in positions:
        try:
            q = await fmp.get_quote(pos.symbol)
            current_price = float(q.get("price", 0))
        except Exception:
            current_price = 0.0
        market_value = current_price * float(pos.shares)
        cost_basis = float(pos.avg_cost) * float(pos.shares)
        rows.append({
            "symbol": pos.symbol,
            "shares": float(pos.shares),
            "avg_cost": float(pos.avg_cost),
            "current_price": current_price,
            "market_value": market_value,
            "unrealised_pnl": market_value - cost_basis,
        })
    return rows


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)):
    user = await _get_or_create_user(db)
    result = await db.execute(select(Position).where(Position.user_id == DEFAULT_USER_ID))
    positions = result.scalars().all()

    equity = Decimal(0)
    for pos in positions:
        try:
            q = await fmp.get_quote(pos.symbol)
            price = Decimal(str(q.get("price", 0)))
        except Exception:
            price = pos.avg_cost
        equity += price * pos.shares

    total_value = user.cash_balance + equity
    pnl = total_value - user.initial_deposit
    pnl_pct = (float(pnl) / float(user.initial_deposit) * 100) if user.initial_deposit else 0.0

    return {
        "cash_balance": float(user.cash_balance),
        "equity_value": float(equity),
        "total_value": float(total_value),
        "initial_deposit": float(user.initial_deposit),
        "pnl": float(pnl),
        "pnl_pct": round(pnl_pct, 2),
    }


@router.get("/transactions")
async def transactions(
    symbol: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(Transaction).where(Transaction.user_id == DEFAULT_USER_ID)
    if symbol:
        query = query.where(Transaction.symbol == symbol.upper())
    if from_date:
        query = query.where(Transaction.timestamp >= datetime.fromisoformat(from_date))
    if to_date:
        query = query.where(Transaction.timestamp <= datetime.fromisoformat(to_date))
    query = query.order_by(Transaction.timestamp.desc())
    result = await db.execute(query)
    txns = result.scalars().all()
    return [
        {
            "id": t.id,
            "symbol": t.symbol,
            "type": t.type.value,
            "shares": float(t.shares) if t.shares else None,
            "price": float(t.price) if t.price else None,
            "amount": float(t.amount),
            "timestamp": t.timestamp.isoformat(),
        }
        for t in txns
    ]
