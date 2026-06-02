from fastapi import APIRouter, HTTPException
from backend.services import fmp

router = APIRouter(prefix="/api/market", tags=["market"])


def _fmp_exc_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/quote/{symbol}")
async def quote(symbol: str):
    try:
        return await fmp.get_quote(symbol)
    except (PermissionError, LookupError, RuntimeError) as exc:
        raise _fmp_exc_to_http(exc)


@router.get("/profile/{symbol}")
async def profile(symbol: str):
    try:
        return await fmp.get_profile(symbol)
    except (PermissionError, LookupError, RuntimeError) as exc:
        raise _fmp_exc_to_http(exc)


@router.get("/search")
async def search(q: str, limit: int = 10):
    return await fmp.search_symbol(q, limit)


@router.get("/history/{symbol}")
async def history(symbol: str, from_date: str = "", to_date: str = ""):
    return await fmp.get_history(symbol, from_date, to_date)
