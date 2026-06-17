from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.db import init_db
from backend.routers import market, portfolio, agent, simulation, knowledge, screener
from backend.routers import sessions


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    _init_langfuse()
    yield


app = FastAPI(title="Quant Agentic Trading API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}
