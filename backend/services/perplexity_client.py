"""
Deep-research specialist agent backed by Perplexity.

Talks to an OpenAI-compatible /chat/completions endpoint. By default this is the
self-hosted perplexity-scrape proxy (https://github.com/mrdzer0/perplexity-scrape),
which impersonates a Perplexity Pro browser session via PERPLEXITY_SESSION_TOKEN.

To switch to the official, ToS-clean Sonar API (returns real citation URLs), set:
    PERPLEXITY_BASE_URL=https://api.perplexity.ai
    PERPLEXITY_API_KEY=pplx-...
    PERPLEXITY_MODEL=sonar-pro
…with no code change. PERPLEXITY_BASE_URL is the base up to (not including)
/chat/completions — scrape proxy: http://127.0.0.1:8045/v1 ; Sonar: https://api.perplexity.ai
"""
from __future__ import annotations

import os

import httpx

from backend.services.llm_logger import LLMLogger

PERPLEXITY_BASE_URL = os.getenv("PERPLEXITY_BASE_URL", "http://127.0.0.1:8045/v1")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY", "")  # scrape proxy: may be empty
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "claude45sonnetthinking")
PERPLEXITY_TIMEOUT = float(os.getenv("PERPLEXITY_TIMEOUT", "120"))

_MAX_HISTORY_MSGS = 6  # recent turns for follow-up context (skips the bulky skill-init turn)

RESEARCH_SYSTEM = (
    "You are a financial deep-research analyst. Answer the user's question using current, "
    "real-world information from the web. Lead with the direct answer, then supporting detail. "
    "Attribute figures and claims to their source inline, and note the recency of time-sensitive "
    "data. Be concise and factual. Clearly distinguish reported facts from forecasts or opinions."
)


def _history_to_openai(history: list[dict] | None) -> list[dict]:
    """Flatten bedrock-format history to plain OpenAI text messages (drops tool blocks)."""
    out: list[dict] = []
    for msg in (history or [])[-_MAX_HISTORY_MSGS:]:
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        else:
            text = " ".join(
                b.get("text", "") for b in content if isinstance(b, dict) and b.get("text")
            )
        if text.strip():
            out.append({"role": msg["role"], "content": text})
    return out


def _format_citations(data: dict) -> str:
    """Render a Sources footer from Sonar-style citations/search_results, if present."""
    citations = data.get("citations") or data.get("search_results") or []
    urls: list[str] = []
    for c in citations:
        if isinstance(c, str):
            urls.append(c)
        elif isinstance(c, dict):
            url = c.get("url") or c.get("link")
            if url:
                title = c.get("title")
                urls.append(f"{title} — {url}" if title else url)
    if not urls:
        return ""
    lines = "\n".join(f"{i}. {u}" for i, u in enumerate(urls, 1))
    return f"\n\n**Sources:**\n{lines}"


async def research(
    message: str,
    history: list[dict] | None = None,
    session_id: str = "",
) -> str:
    """One deep-research turn via the Perplexity-backed OpenAI-compatible endpoint."""
    messages = [{"role": "system", "content": RESEARCH_SYSTEM}]
    messages.extend(_history_to_openai(history))
    messages.append({"role": "user", "content": message})

    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"} if PERPLEXITY_API_KEY else {}

    async with LLMLogger("perplexity", PERPLEXITY_MODEL, session_id, message) as trace:
        async with httpx.AsyncClient(timeout=PERPLEXITY_TIMEOUT, headers=headers) as client:
            try:
                resp = await client.post(
                    f"{PERPLEXITY_BASE_URL}/chat/completions",
                    json={"model": PERPLEXITY_MODEL, "messages": messages, "stream": False},
                )
                resp.raise_for_status()
            except httpx.ConnectError:
                reply = (
                    "Research provider unreachable. Start the perplexity-scrape proxy "
                    "(or set PERPLEXITY_BASE_URL to the Sonar API) and try again."
                )
                trace.finish(reply)
                return reply
            except httpx.TimeoutException:
                reply = "Research request timed out. Please try again."
                trace.finish(reply)
                return reply
            except httpx.HTTPStatusError as exc:
                reply = f"Research provider error {exc.response.status_code}: {exc.response.text[:200]}"
                trace.finish(reply)
                return reply

            data = resp.json()
            try:
                reply = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                reply = "Research provider returned an unexpected response."
                trace.finish(reply)
                return reply

            reply += _format_citations(data)

            usage = data.get("usage") or {}
            trace.finish(
                reply,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
            return reply
