from fastapi import APIRouter
from backend.services import fmp

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/quote/{symbol}")
async def quote(symbol: str):
    return await fmp.get_quote(symbol)


@router.get("/profile/{symbol}")
async def profile(symbol: str):
    return await fmp.get_profile(symbol)


@router.get("/search")
async def search(q: str, limit: int = 10):
    return await fmp.search_symbol(q, limit)


@router.get("/history/{symbol}")
async def history(symbol: str, from_date: str = "", to_date: str = ""):
    return await fmp.get_history(symbol, from_date, to_date)
