"""
Copilot orchestrator — routes a user message to the right specialist agent.

Specialists:
  - "advice"   → backend.services.bedrock / ollama_client (tool-equipped: quotes,
                 portfolio, theses, principles, screener history). The user's
                 configured provider/model.
  - "research" → backend.services.perplexity_client (current web info, no local tools).
  - "both"     → research first, then feed findings into the advice agent for synthesis.

Routing is one cheap Bedrock-Haiku classification call. When Bedrock is unavailable
it falls back to Ollama Cloud, then local Ollama, and finally a keyword heuristic so
Ollama-only / Bedrock-less setups still route deterministically.
"""
from __future__ import annotations

import asyncio
import os
from typing import Optional

VALID_INTENTS = {"advice", "research", "both"}

_ROUTER_SYSTEM = (
    "You are an intent router for a trading copilot. Classify the user's message into exactly one:\n"
    "- research: needs CURRENT real-world info from the web — latest news, recent events, "
    "today's analyst views, breaking developments, 'what's happening with', macro updates.\n"
    "- advice: can be answered from the user's portfolio, live quotes, uploaded research theses, "
    "screener history, or investing principles — analysis, valuation, strategy, 'what do you think of'.\n"
    "- both: needs fresh web context AND portfolio/principles reasoning to answer well.\n"
    "Reply with ONLY the single word: research, advice, or both."
)

# Keyword fallback when the Haiku router is unavailable (no Bedrock creds).
_RESEARCH_HINTS = (
    "latest", "news", "today", "recent", "breaking", "this week", "this morning",
    "happening", "announced", "just ", "current events", "headline",
)


def _keyword_route(message: str) -> str:
    m = message.lower()
    return "research" if any(h in m for h in _RESEARCH_HINTS) else "advice"


def _match_intent(text: str) -> Optional[str]:
    """Pull the first valid intent word out of a raw LLM reply, or None."""
    word = (text or "").strip().lower()
    for intent in VALID_INTENTS:
        if intent in word:
            return intent
    return None


def _classify_bedrock(message: str) -> Optional[str]:
    """Cheap Bedrock-Haiku classification. Returns None if Bedrock is unavailable."""
    import boto3

    region = os.getenv("BEDROCK_REGION", "eu-west-1")
    # Prefer a fast/cheap model for routing; fall back to the main one.
    model_id = os.getenv("BEDROCK_ROUTER_MODEL_ID") or os.getenv(
        "BEDROCK_MODEL_ID", "eu.anthropic.claude-haiku-4-5"
    )
    client = boto3.client("bedrock-runtime", region_name=region)
    resp = client.converse(
        modelId=model_id,
        system=[{"text": _ROUTER_SYSTEM}],
        messages=[{"role": "user", "content": [{"text": message}]}],
        inferenceConfig={"maxTokens": 4, "temperature": 0.0},
    )
    return _match_intent(resp["output"]["message"]["content"][0]["text"])


async def _classify_ollama(message: str, *, cloud: bool) -> Optional[str]:
    """Route via Ollama (cloud or local). Returns None on failure or no match."""
    from backend.services import ollama_client

    if cloud:
        api_key = os.getenv("OLLAMA_API_KEY", "")
        if not api_key:
            return None
        model = ollama_client.OLLAMA_CLOUD_DEFAULT_MODEL
        host = ollama_client.OLLAMA_CLOUD_HOST
    else:
        api_key = ""
        model = ollama_client.OLLAMA_DEFAULT_MODEL
        host = ollama_client.OLLAMA_HOST

    reply = await ollama_client.classify_text(
        _ROUTER_SYSTEM, message, model=model, host=host, api_key=api_key
    )
    return _match_intent(reply)


async def classify_intent(message: str) -> str:
    """
    Return 'advice' | 'research' | 'both'.

    Fallback chain: Bedrock → Ollama Cloud → local Ollama → keyword heuristic.
    """
    try:
        intent = await asyncio.to_thread(_classify_bedrock, message)
        if intent:
            return intent
    except Exception:
        pass

    for cloud in (True, False):
        try:
            intent = await _classify_ollama(message, cloud=cloud)
            if intent:
                return intent
        except Exception:
            continue

    return _keyword_route(message)


def build_synthesis_input(original_message: str, research_findings: str) -> str:
    """Wrap research output as grounding context for the advice agent in a 'both' flow."""
    return (
        f"{original_message}\n\n"
        "---\n"
        "Deep-research findings from the web (treat as current external context; "
        "verify against principles and the user's portfolio before advising):\n\n"
        f"{research_findings}"
    )
