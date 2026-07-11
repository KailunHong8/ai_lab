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


def format_citations_footer(citations: list[dict]) -> str:
    """Render a Sources footer from a normalised [{url, title}] citation list."""
    urls: list[str] = []
    for c in citations:
        url = c.get("url")
        if url:
            title = c.get("title")
            urls.append(f"{title} — {url}" if title else url)
    if not urls:
        return ""
    lines = "\n".join(f"{i}. {u}" for i, u in enumerate(urls, 1))
    return f"\n\n**Sources:**\n{lines}"


async def _call_perplexity(messages: list[dict], session_id: str, user_message: str) -> dict:
    """
    Shared transport layer. Returns raw API response dict, or raises on error.
    Caller is responsible for LLMLogger context.
    """
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}"} if PERPLEXITY_API_KEY else {}
    async with httpx.AsyncClient(timeout=PERPLEXITY_TIMEOUT, headers=headers) as client:
        resp = await client.post(
            f"{PERPLEXITY_BASE_URL}/chat/completions",
            json={"model": PERPLEXITY_MODEL, "messages": messages, "stream": False},
        )
        resp.raise_for_status()
    return resp.json()


async def research(
    message: str,
    history: list[dict] | None = None,
    session_id: str = "",
) -> str:
    """One deep-research turn via the Perplexity-backed OpenAI-compatible endpoint."""
    messages = [{"role": "system", "content": RESEARCH_SYSTEM}]
    messages.extend(_history_to_openai(history))
    messages.append({"role": "user", "content": message})

    async with LLMLogger("perplexity", PERPLEXITY_MODEL, session_id, message) as trace:
        try:
            data = await _call_perplexity(messages, session_id, message)
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


async def research_raw(
    query: str,
    history: list[dict] | None = None,
    session_id: str = "",
) -> dict:
    """
    Run a Perplexity query and return structured output for ingestion.

    Returns:
        {
            "content": str,           # full answer text (no citation footer appended)
            "citations": list[dict],  # [{url, title}] list
            "input_tokens": int,
            "output_tokens": int,
        }

    Raises httpx exceptions on transport failure — caller should handle.
    """
    messages = [{"role": "system", "content": RESEARCH_SYSTEM}]
    messages.extend(_history_to_openai(history))
    messages.append({"role": "user", "content": query})

    async with LLMLogger("perplexity", PERPLEXITY_MODEL, session_id, query) as trace:
        data = await _call_perplexity(messages, session_id, query)

        content = ""
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            pass

        raw_citations = data.get("citations") or data.get("search_results") or []
        citations: list[dict] = []
        for c in raw_citations:
            if isinstance(c, str):
                citations.append({"url": c, "title": ""})
            elif isinstance(c, dict):
                citations.append({
                    "url": c.get("url") or c.get("link") or "",
                    "title": c.get("title") or "",
                })

        usage = data.get("usage") or {}
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        trace.finish(content, input_tokens=input_tokens, output_tokens=output_tokens)

        return {
            "content": content,
            "citations": citations,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
