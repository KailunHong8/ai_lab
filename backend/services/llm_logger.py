"""
LLM observability layer.

Always active: structlog JSON lines → logs/llm.jsonl
Optional:       Langfuse v4 trace (set LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY in .env)

Usage:
    from backend.services.llm_logger import LLMLogger
    async with LLMLogger("bedrock", model_id, session_id, user_message) as trace:
        trace.add_tool_use("get_quote", {"symbol": "NVDA"}, '{"price": 135}')
        reply = await bedrock.chat(...)
        trace.finish(reply, input_tokens=..., output_tokens=...)
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

import structlog

# ── structlog setup ───────────────────────────────────────────────────────────

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)
_LOG_FILE = _LOG_DIR / "llm.jsonl"

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(
        file=open(_LOG_FILE, "a", buffering=1)  # noqa: SIM115 — intentional append
    ),
)

_log = structlog.get_logger()

# ── optional Langfuse v4 ──────────────────────────────────────────────────────

_langfuse = None
_langfuse_init_attempted = False


def _get_langfuse():
    global _langfuse, _langfuse_init_attempted
    if _langfuse is not None:
        return _langfuse
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    if not pk or not sk:
        return None
    if _langfuse_init_attempted:
        return None
    _langfuse_init_attempted = True
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(public_key=pk, secret_key=sk, host=host)
    except Exception:
        pass
    return _langfuse


# ── trace context manager ─────────────────────────────────────────────────────

class LLMLogger:
    def __init__(
        self,
        provider: str,
        model: str,
        session_id: str = "",
        user_message: str = "",
    ):
        self.provider = provider
        self.model = model
        self.session_id = session_id
        self.user_message = user_message
        self._start = 0.0
        self._tool_calls: list[dict] = []
        # LangFuse v4 observation handles
        self._lf_agent = None    # top-level agent span (acts as the trace)
        self._lf_gen = None      # generation child span

    async def __aenter__(self):
        self._start = time.monotonic()
        lf = _get_langfuse()
        if lf:
            try:
                # Top-level "agent" span — groups everything under one trace
                self._lf_agent = lf.start_observation(
                    name="copilot-turn",
                    as_type="agent",
                    input=self.user_message,
                    metadata={"provider": self.provider, "model": self.model,
                               "session_id": self.session_id or None},
                )
                # Generation child — records model, tokens, latency
                self._lf_gen = self._lf_agent.start_observation(
                    name="llm-call",
                    as_type="generation",
                    model=self.model,
                    input=self.user_message,
                )
            except Exception:
                self._lf_agent = None
                self._lf_gen = None
        return self

    def add_tool_use(self, tool_name: str, tool_input: dict, tool_result: str) -> None:
        self._tool_calls.append({
            "tool": tool_name,
            "input": tool_input,
            "result_len": len(tool_result),
        })
        _log.info(
            "llm_tool_use",
            provider=self.provider,
            model=self.model,
            session_id=self.session_id,
            tool=tool_name,
            input=tool_input,
        )
        if self._lf_agent:
            try:
                # Tool spans are children of the agent, siblings of the generation
                self._lf_agent.start_observation(
                    name=f"tool:{tool_name}",
                    as_type="tool",
                    input=tool_input,
                    output=tool_result[:500],
                ).end()
            except Exception:
                pass

    def finish(
        self,
        reply: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        latency_ms = int((time.monotonic() - self._start) * 1000)
        _log.info(
            "llm_turn",
            provider=self.provider,
            model=self.model,
            session_id=self.session_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            tool_calls=len(self._tool_calls),
            tools_used=[t["tool"] for t in self._tool_calls],
        )
        if self._lf_gen:
            try:
                self._lf_gen.update(
                    output=reply,
                    usage_details={"input": input_tokens, "output": output_tokens},
                    metadata={"latency_ms": latency_ms},
                )
                self._lf_gen.end()
            except Exception:
                pass
        if self._lf_agent:
            try:
                self._lf_agent.update(output=reply[:500])
                self._lf_agent.end()
            except Exception:
                pass

    async def __aexit__(self, *_):
        lf = _get_langfuse()
        if lf:
            try:
                lf.flush()
            except Exception:
                pass
