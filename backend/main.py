from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import init_db
from backend.routers import market, portfolio, agent, simulation, knowledge, screener
from backend.routers import sessions, strategies


def _init_langfuse():
    """Initialize LangFuse at startup with visible diagnostics."""
    from backend.services import llm_logger

    # Reset cached state so every server restart gets a fresh attempt
    llm_logger._langfuse = None
    llm_logger._langfuse_init_attempted = False

    lf = llm_logger._get_langfuse()
    if lf:
        host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        print(f"✓ LangFuse tracing enabled → {host}")
    elif not os.getenv("LANGFUSE_PUBLIC_KEY"):
        print("⚠ LangFuse disabled: LANGFUSE_PUBLIC_KEY not set in .env")
    else:
        print("✗ LangFuse init failed — check LANGFUSE_HOST and keys in .env")


async def _cleanup_expired_on_startup() -> None:
    """Best-effort: remove expired market-opinion docs at startup. Never blocks startup."""
    try:
        from backend.db import SessionLocal
        from backend.routers.knowledge import remove_expired_market_opinion
        async with SessionLocal() as db:
            removed = await remove_expired_market_opinion(db)
        if removed:
            print(f"✓ Startup cleanup: removed {removed} expired market-opinion document(s)")
    except Exception as exc:
        print(f"⚠ Startup cleanup failed (non-fatal): {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    _init_langfuse()
    await _cleanup_expired_on_startup()
    yield


app = FastAPI(title="Quant Agentic Trading API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(portfolio.router)
app.include_router(agent.router)
app.include_router(simulation.router)
app.include_router(knowledge.router)
app.include_router(screener.router)
app.include_router(sessions.router)
app.include_router(strategies.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
