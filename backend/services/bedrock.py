"""
AWS Bedrock Converse API wrapper with tool-use support.

Tools available to the agent:
  - get_quote(symbol)              → FMP/Yahoo real-time quote
  - get_portfolio()                → current user holdings from DB
  - search_theses(entity, theme)   → current market opinions from uploaded research
  - get_entity_graph(symbol)       → supply chain / competitor / customer graph
  - search_principles(query)       → timeless investing principles from the book library
"""
from __future__ import annotations

import json
import os
import boto3
from dotenv import load_dotenv

from backend.services import fmp as fmp_service

load_dotenv()

BEDROCK_REGION = os.getenv("BEDROCK_REGION", "eu-west-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")

_bedrock = None


def _client():
    global _bedrock
    if _bedrock is None:
        _bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _bedrock


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
]

SYSTEM_PROMPT = (
    "You are Quant, an AI trading copilot with access to two distinct knowledge sources — "
    "treat them very differently:\n\n"
    "1. INVESTING PRINCIPLES (search_principles tool): A curated library of classic investing and finance books "
    "(Brealey-Myers-Allen, Shiller, Poor Charlie's Almanack, and others added over time). "
    "This is established theory and timeless wisdom. Treat it as ground truth. "
    "Use it to frame the 'why' — valuation logic, risk models, mental models, capital allocation discipline.\n\n"
    "2. CURRENT MARKET OPINIONS (search_theses tool): Research uploaded by the user — newsletters, ARK reports, "
    "analyst notes, etc. These may be forecasts or opinions. Always label them as such and note the source and date. "
    "Use them for the 'what and when' — specific stocks, near-term themes, catalysts.\n\n"
    "Reasoning pattern: ground every investment argument in principles first, then layer on current opinions. "
    "For example: 'Brealey's CAPM implies a required return of X% for this beta — ARK's thesis forecasts Y%, "
    "which clears that hurdle [or does not].'\n\n"
    "You also have access to real-time market data and the user's paper-trading portfolio. "
    "Always cite which source (book title, or thesis source + date) your reasoning draws from. "
    "Never confuse a verified fact with a forecast. "
    "You operate in a paper-trading simulation — no real money is at risk."
)


async def _dispatch_tool(name: str, tool_input: dict, portfolio_snapshot: dict | None) -> str:
    if name == "get_quote":
        symbol = tool_input.get("symbol", "")
        try:
            data = await fmp_service.get_quote(symbol)
            return json.dumps(data)
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
            results = await search_theses(entity, theme, limit=8, db=db)
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
        results = search_principles(tool_input.get("query", ""), top_k=4)
        return json.dumps(results)

    return json.dumps({"error": f"unknown tool: {name}"})


async def chat(
    message: str,
    history: list[dict],
    portfolio_snapshot: dict | None = None,
) -> str:
    """
    Run one agentic turn.

    `history` is a list of {role, content} dicts for the ongoing session.
    Returns the assistant's final text reply.
    """
    messages = list(history) + [{"role": "user", "content": [{"text": message}]}]

    client = _client()

    while True:
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=messages,
            toolConfig={"tools": TOOLS},
        )

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
                return block["text"]

        return ""
