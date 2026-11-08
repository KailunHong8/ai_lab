"""
Hosted LLM client — AI Model Router (primary) with AWS Bedrock as fallback.

Both backends expose the Bedrock Converse API shape (``client.converse(...)``), so
callers stay provider-agnostic. The router is Anthropic-Messages compatible and is
preferred whenever ``AI_MODEL_ROUTER_API_KEY`` is configured; otherwise calls go to
Bedrock. Pass provider="bedrock" to force Bedrock.

Providers handled here: "router" (default) and "bedrock" (legacy fallback).
Ollama lives in ``ollama_client``.

Tools available to the agent:
  - get_quote(symbol)               → FMP/Yahoo real-time quote
  - get_portfolio()                 → current user holdings from DB
  - search_theses(entity, theme)    → structured investment theses from all funds
  - get_entity_graph(symbol)        → supply chain / competitor / customer graph
  - search_principles(query)        → timeless investing principles from the book library
  - search_market_opinion(query)    → semantic search over fund letters + Perplexity web research
  - get_screener_history(limit)     → historical stock screener runs
"""
from __future__ import annotations

import asyncio
import functools
import json
import os

import boto3
import httpx
from botocore.config import Config
from dotenv import load_dotenv

from backend.services import market_data as market_data_service

load_dotenv()

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "eu-west-1")
BEDROCK_DEFAULT_MODEL = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
AWS_PROFILE = os.getenv("AWS_PROFILE")

ROUTER_BASE_URL = os.getenv(
    "AI_MODEL_ROUTER_BASE_URL",
    "https://ai-model-router-api.eu.foundations.prod.int.hellofresh.io",
).rstrip("/")
ROUTER_API_KEY = os.getenv("AI_MODEL_ROUTER_API_KEY", "")
ROUTER_DEFAULT_MODEL = os.getenv("AI_MODEL_ROUTER_MODEL", "Fast")
ROUTER_MAX_TOKENS = int(os.getenv("AI_MODEL_ROUTER_MAX_TOKENS", "8192"))

# Bedrock-style model ids. Anything else is a router model id.
_BEDROCK_ID_PREFIXES = ("eu.anthropic.", "global.anthropic.", "anthropic.", "us.anthropic.")

_router = None
_bedrock = None


def router_available() -> bool:
    return bool(ROUTER_API_KEY)


def resolve(provider: str, model: str | None) -> tuple[str, str]:
    """
    Map a requested provider + model onto the backend actually used.

    Returns (backend, model_id) where backend is "router" or "bedrock".
    "router" falls back to Bedrock when no router key is configured; either way a
    model id belonging to the other backend is replaced by that backend's default.
    """
    backend = "bedrock" if provider == "bedrock" or not ROUTER_API_KEY else "router"
    model_id = model or (BEDROCK_DEFAULT_MODEL if backend == "bedrock" else ROUTER_DEFAULT_MODEL)
    if backend == "router" and model_id.startswith(_BEDROCK_ID_PREFIXES):
        model_id = ROUTER_DEFAULT_MODEL
    elif backend == "bedrock" and not model_id.startswith(_BEDROCK_ID_PREFIXES):
        model_id = BEDROCK_DEFAULT_MODEL
    return backend, model_id


def router_models() -> list[str]:
    """Model ids served by the router catalog; [] when the router is not configured."""
    if not ROUTER_API_KEY:
        return []
    try:
        response = httpx.get(
            f"{ROUTER_BASE_URL}/v1/models",
            headers={
                "Authorization": f"Bearer {ROUTER_API_KEY}",
                "anthropic-version": "2023-06-01",
            },
            timeout=10,
        )
        response.raise_for_status()
        ids = [m["id"] for m in response.json().get("data", []) if isinstance(m.get("id"), str)]
        return ids or [ROUTER_DEFAULT_MODEL]
    except Exception:
        return [ROUTER_DEFAULT_MODEL]


class RouterClient:
    """Anthropic-Messages client that mimics the Bedrock Converse API."""

    def converse(self, **kwargs):
        model_id = kwargs.get("modelId") or ROUTER_DEFAULT_MODEL

        body = {
            "model": model_id,
            "max_tokens": ROUTER_MAX_TOKENS,
            "messages": [self._message(message) for message in kwargs.get("messages", [])],
        }
        system = kwargs.get("system", [])
        if system:
            body["system"] = "\n".join(block["text"] for block in system if "text" in block)

        inference = kwargs.get("inferenceConfig", {})
        if "maxTokens" in inference:
            body["max_tokens"] = inference["maxTokens"]
        for source, target in (("temperature", "temperature"), ("topP", "top_p")):
            if source in inference:
                body[target] = inference[source]

        tools = kwargs.get("toolConfig", {}).get("tools", [])
        if tools:
            body["tools"] = [
                {
                    "name": tool["toolSpec"]["name"],
                    "description": tool["toolSpec"].get("description", ""),
                    "input_schema": tool["toolSpec"]["inputSchema"]["json"],
                }
                for tool in tools
            ]

        response = httpx.post(
            f"{ROUTER_BASE_URL}/v1/messages",
            headers={
                "Authorization": f"Bearer {ROUTER_API_KEY}",
                "anthropic-version": "2023-06-01",
            },
            json=body,
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        content = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content.append({"text": block["text"]})
            elif block.get("type") == "tool_use":
                content.append({
                    "toolUse": {
                        "toolUseId": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    }
                })

        stop_reason = data.get("stop_reason")
        return {
            "output": {"message": {"role": "assistant", "content": content}},
            "stopReason": "tool_use" if stop_reason == "tool_use" else (
                "max_tokens" if stop_reason == "max_tokens" else "end_turn"
            ),
            "usage": {
                "inputTokens": data.get("usage", {}).get("input_tokens", 0),
                "outputTokens": data.get("usage", {}).get("output_tokens", 0),
            },
        }

    @staticmethod
    def _message(message: dict) -> dict:
        content = []
        for block in message.get("content", []):
            if "text" in block:
                content.append({"type": "text", "text": block["text"]})
            elif "toolUse" in block:
                tool_use = block["toolUse"]
                content.append({
                    "type": "tool_use",
                    "id": tool_use["toolUseId"],
                    "name": tool_use["name"],
                    "input": tool_use.get("input", {}),
                })
            elif "toolResult" in block:
                tool_result = block["toolResult"]
                result_content = tool_result.get("content", [])
                content.append({
                    "type": "tool_result",
                    "tool_use_id": tool_result["toolUseId"],
                    "content": "\n".join(
                        item["text"] for item in result_content if "text" in item
                    ),
                })
        return {"role": message["role"], "content": content}


def _client(backend: str):
    global _router, _bedrock
    if backend == "router":
        if _router is None:
            _router = RouterClient()
        return _router
    if _bedrock is None:
        session = boto3.Session(profile_name=AWS_PROFILE)
        _bedrock = session.client(
            "bedrock-runtime",
            region_name=BEDROCK_REGION,
            config=Config(read_timeout=300),
        )
    return _bedrock


def complete_sync(provider: str, model: str | None, **kwargs) -> dict:
    """Blocking single-shot converse. Wrap in asyncio.to_thread from async code."""
    backend, model_id = resolve(provider, model)
    return _client(backend).converse(modelId=model_id, **kwargs)


TOOLS = [
    {
        "toolSpec": {
            "name": "get_quote",
            "description": "Fetch a real-time stock quote (price, change, volume, market cap) for a given ticker symbol.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL"}
                    },
                    "required": ["symbol"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_portfolio",
            "description": "Return the current user's portfolio holdings, cash balance, equity value, and P&L.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_theses",
            "description": (
                "Search the structured investment thesis database for research insights. "
                "Returns theses with entity stance, claims (facts or forecasts), theme, and date. "
                "Use this to answer questions like 'What is ARK's thesis on NVDA?' or "
                "'What are the bullish arguments for AI infrastructure?'"
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "entity": {
                            "type": "string",
                            "description": "Ticker symbol to filter by, e.g. NVDA. Leave empty to search across all entities."
                        },
                        "theme": {
                            "type": "string",
                            "description": "Investment theme to filter by, e.g. 'AI Infrastructure', 'EV'. Leave empty to search all themes."
                        },
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_entity_graph",
            "description": (
                "Get the supply chain, competitor, and customer relationships for a stock. "
                "Use this to understand which holdings may be affected when a key company is mentioned in research. "
                "For example, if a newsletter is bullish on NVDA, this tool reveals NVDA's customers (MSFT, META, AMZN) "
                "and suppliers (TSMC, SK Hynix) that may be indirectly impacted."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Ticker symbol, e.g. NVDA"}
                    },
                    "required": ["symbol"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_screener_history",
            "description": (
                "Retrieve the user's historical stock screener runs from the database. "
                "Returns the most recent value screens with their tickers, criteria, pass/fail results, "
                "and key fundamentals (P/E, P/B, ROE, ROA, D/E, etc.) for each stock. "
                "Use this to reference previous screens in strategy discussions, compare how a stock "
                "scored across different dates, or identify stocks that consistently pass quality filters."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "How many recent runs to fetch (default 5, max 20)."
                        }
                    },
                    "required": [],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_principles",
            "description": (
                "Search a curated library of investing and finance books "
                "(currently: Brealey-Myers-Allen Principles of Corporate Finance, "
                "Shiller Finance and the Good Society, Poor Charlie's Almanack). "
                "Use this to ground reasoning in established theory, mental models, and "
                "long-term investing philosophy. These are timeless principles, not market opinions. "
                "Call this when the user asks about valuation frameworks, risk models, CAPM, "
                "diversification, mental models, or any foundational investing concept."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic or concept to look up, e.g. 'CAPM risk premium', 'mental models checklist', 'NPV capital budgeting'"
                        }
                    },
                    "required": ["query"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_market_opinion",
            "description": (
                "Semantic search over the market-opinion corpus: fund letters (ARK, GMO, Sequoia, "
                "Bridgewater) and Perplexity web research. "
                "Use for open-ended recall questions like 'what did ARK say about energy storage?' "
                "or 'what is the current market view on AI capex?'. "
                "Returns citation snippets with source and recency metadata. "
                "Optionally filter by fund (e.g. 'ARK') or source_type ('fund_letter' or 'web_research'). "
                "For precise structured stance questions use search_theses; for open-ended recall use this."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Topic or phrase to search for"
                        },
                        "fund": {
                            "type": "string",
                            "description": "Optional: filter to a specific fund, e.g. 'ARK', 'GMO', 'Sequoia', 'Bridgewater'"
                        },
                        "source_type": {
                            "type": "string",
                            "description": "Optional: 'fund_letter' or 'web_research'"
                        },
                    },
                    "required": ["query"],
                }
            },
        }
    },
]

SYSTEM_PROMPT = (
    "You are Quant, an AI trading copilot. You have access to four tiers of knowledge — "
    "always reason in this order and never collapse the tiers:\n\n"
    "TIER 1 — INVESTING PRINCIPLES (search_principles tool, reliability: highest): "
    "A curated library of classic finance and investing books. "
    "This is established theory and timeless wisdom. Treat it as ground truth. "
    "Use it to frame the 'why' — valuation logic, risk models, mental models, capital allocation discipline.\n\n"
    "TIER 2 — FUND LETTERS (search_theses + search_market_opinion filtered to fund_letter, reliability: high): "
    "Structured theses and raw text from curated fund letters (ARK, GMO, Sequoia, Bridgewater, and others). "
    "These are expert opinions, not facts. Always label the fund, date, and whether the claim is a fact or forecast.\n\n"
    "TIER 3 — WEB RESEARCH / MARKET SENTIMENT (search_market_opinion filtered to web_research, reliability: lower): "
    "Perplexity-sourced market context. Time-sensitive; check the ingestion date and note if potentially stale. "
    "Never use this as the sole basis for a recommendation.\n\n"
    "Reasoning pattern: ground every investment argument in TIER 1 principles first, layer fund opinions second, "
    "add web context last as supporting colour. "
    "Example: 'Brealey's CAPM implies a required return of X% for this beta — "
    "ARK's thesis (2025-03) forecasts Y%, which clears that hurdle [or does not]. "
    "Current market sentiment (Perplexity, 2026-06) notes Z as a near-term risk.'\n\n"
    "RULES:\n"
    "- Always cite source (book title, or fund + date, or 'Perplexity web research, ingested YYYY-MM-DD').\n"
    "- Explicitly label FACT vs FORECAST for every claim.\n"
    "- Never use market sentiment alone as the core recommendation basis.\n"
    "- When discussing specific stocks, check get_screener_history for how they scored in past value screens.\n"
    "- If search_theses returns no stored research for a ticker, call get_quote for that ticker and "
    "base the analysis on live market data, clearly noting that no curated research was available.\n\n"
    "You also have access to real-time market data and the user's paper-trading portfolio. "
    "No real money is at risk."
)


async def _dispatch_tool(name: str, tool_input: dict, portfolio_snapshot: dict | None) -> str:
    if name == "get_quote":
        symbol = tool_input.get("symbol", "").strip().upper()
        try:
            from backend.services import fmp as fmp_service

            quote = await fmp_service.get_quote(symbol)
            if not quote or quote.get("price") is None:
                return json.dumps({
                    "error": f"No quote data available for {symbol} from FMP or Yahoo Finance."
                })
            return json.dumps({
                "symbol": quote.get("symbol", symbol),
                "name": quote.get("name", ""),
                "price": quote["price"],
                "change_pct": quote.get("changesPercentage", 0),
                "volume": quote.get("volume"),
                "market_cap": quote.get("marketCap"),
                "open": quote.get("open"),
                "day_high": quote.get("dayHigh"),
                "day_low": quote.get("dayLow"),
            })
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    if name == "get_portfolio":
        return json.dumps(portfolio_snapshot or {"error": "portfolio not available"})

    if name == "search_theses":
        from backend.db import SessionLocal
        from backend.services.knowledge_base import search_theses
        entity = tool_input.get("entity") or None
        theme = tool_input.get("theme") or None
        async with SessionLocal() as db:
            results = await search_theses(entity, theme, limit=8, db=db, exclude_stale=True)
        if not results and entity:
            # No stored research on this ticker — signal the agent to fall back to
            # a live quote for fresh analysis instead of claiming no information.
            return json.dumps({
                "results": [],
                "note": (
                    f"No stored theses for {entity.upper()} in the knowledge base. "
                    f"Call get_quote('{entity.upper()}') for live market data and base "
                    f"the analysis on that instead."
                ),
            })
        return json.dumps(results)

    if name == "get_entity_graph":
        from backend.db import SessionLocal
        from backend.services.knowledge_base import get_entity_graph
        symbol = tool_input.get("symbol", "")
        async with SessionLocal() as db:
            result = await get_entity_graph(symbol, db)
        return json.dumps(result)

    if name == "search_principles":
        from backend.services.research import search_principles
        results = search_principles(tool_input.get("query", ""), top_k=8)
        return json.dumps(results)

    if name == "search_market_opinion":
        from backend.services.market_opinion_research import search_market_opinion
        results = search_market_opinion(
            tool_input.get("query", ""),
            top_k=6,
            fund=tool_input.get("fund") or None,
            source_type=tool_input.get("source_type") or None,
        )
        return json.dumps(results)

    if name == "get_screener_history":
        import httpx as _httpx
        limit = min(int(tool_input.get("limit") or 5), 20)
        try:
            async with _httpx.AsyncClient(timeout=10) as _client:
                resp = await _client.get(
                    "http://localhost:8000/api/screener/history",
                    params={"limit": limit},
                )
                return resp.text
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    return json.dumps({"error": f"unknown tool: {name}"})


async def chat(
    message: str,
    history: list[dict],
    portfolio_snapshot: dict | None = None,
    session_id: str = "",
    model_id: str | None = None,
    provider: str = "router",
) -> str:
    """
    Run one agentic turn. Emits structured logs via LLMLogger (structlog + optional Langfuse).
    """
    from backend.services.llm_logger import LLMLogger

    messages = list(history) + [{"role": "user", "content": [{"text": message}]}]
    backend, selected_model_id = resolve(provider, model_id)
    client = _client(backend)
    total_input_tokens = 0
    total_output_tokens = 0

    async with LLMLogger(backend, selected_model_id, session_id, message) as trace:
        while True:
            response = await asyncio.to_thread(
                functools.partial(
                    client.converse,
                    modelId=selected_model_id,
                    system=[{"text": SYSTEM_PROMPT}],
                    messages=messages,
                    toolConfig={"tools": TOOLS},
                )
            )

            usage = response.get("usage", {})
            total_input_tokens += usage.get("inputTokens", 0)
            total_output_tokens += usage.get("outputTokens", 0)

            output_message = response["output"]["message"]
            messages.append(output_message)
            stop_reason = response["stopReason"]

            if stop_reason == "tool_use":
                tool_results = []
                for block in output_message["content"]:
                    if block.get("toolUse"):
                        tool_use = block["toolUse"]
                        result_str = await _dispatch_tool(
                            tool_use["name"], tool_use["input"], portfolio_snapshot
                        )
                        trace.add_tool_use(tool_use["name"], tool_use["input"], result_str)
                        tool_results.append(
                            {
                                "toolResult": {
                                    "toolUseId": tool_use["toolUseId"],
                                    "content": [{"text": result_str}],
                                }
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                continue

            # end_turn or max_tokens
            for block in output_message["content"]:
                if "text" in block:
                    trace.finish(
                        block["text"],
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                    )
                    return block["text"]

            trace.finish("", input_tokens=total_input_tokens, output_tokens=total_output_tokens)
            return ""
