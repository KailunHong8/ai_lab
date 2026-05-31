import os
import httpx
from dotenv import load_dotenv

load_dotenv()

FMP_API_KEY = os.getenv("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/api/v3"


async def get_quote(symbol: str) -> dict:
    url = f"{FMP_BASE}/quote/{symbol.upper()}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"apikey": FMP_API_KEY})
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else {}


async def get_profile(symbol: str) -> dict:
    url = f"{FMP_BASE}/profile/{symbol.upper()}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"apikey": FMP_API_KEY})
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else {}


async def search_symbol(query: str, limit: int = 10) -> list[dict]:
    url = f"{FMP_BASE}/search"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params={"query": query, "limit": limit, "apikey": FMP_API_KEY})
        resp.raise_for_status()
        return resp.json()


async def get_history(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """Return list of OHLCV dicts sorted ascending by date."""
    url = f"{FMP_BASE}/historical-price-full/{symbol.upper()}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url, params={"from": from_date, "to": to_date, "apikey": FMP_API_KEY})
        resp.raise_for_status()
        payload = resp.json()
        historical = payload.get("historical", [])
        # FMP returns newest first; reverse to oldest-first for simulation
        return list(reversed(historical))
