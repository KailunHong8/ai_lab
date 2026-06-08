from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.routers.portfolio import summary as portfolio_summary
from backend.services import bedrock

router = APIRouter(prefix="/api/agent", tags=["agent"])

# In-memory session store: session_id → list of message dicts
_sessions: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    provider: str = "bedrock"   # "bedrock" or "ollama"
    model: str | None = None    # override model; None = use provider default


@router.post("/chat")
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    history = _sessions.setdefault(req.session_id, [])

    portfolio = await portfolio_summary(db=db)

    if req.provider == "ollama":
        from backend.services import ollama_client
        _model = req.model or ollama_client.OLLAMA_DEFAULT_MODEL
        reply = await ollama_client.chat(
            message=req.message,
            history=history,
            portfolio_snapshot=portfolio,
            model=_model,
        )
    else:
        reply = await bedrock.chat(
            message=req.message,
            history=history,
            portfolio_snapshot=portfolio,
        )

    history.append({"role": "user", "content": [{"text": req.message}]})
    history.append({"role": "assistant", "content": [{"text": reply}]})

    return {"reply": reply, "session_id": req.session_id}


@router.delete("/chat/{session_id}")
async def clear_session(session_id: str):
    _sessions.pop(session_id, None)
    return {"cleared": session_id}
