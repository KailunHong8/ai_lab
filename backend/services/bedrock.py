"""
AWS Bedrock Converse API wrapper with tool-use support.

Tools available to the agent:
  - get_quote(symbol)      → FMP real-time quote
  - get_portfolio()        → current user holdings from DB
  - search_research(query) → relevant passages from docs/
"""
from __future__ import annotations

import json
import os
import boto3
from dotenv import load_dotenv

from backend.services import fmp as fmp_service
from backend.services.research import search_research

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
            "description": "Fetch a real-time stock quote from FMP for a given ticker symbol.",
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
            "description": "Return the current user's portfolio holdings, cash balance, and P&L.",
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
            "name": "search_research",
            "description": (
                "Search the investing research library (Shiller 'Finance and the Good Society', "
                "Brealey-Myers-Allen 'Principles of Corporate Finance') for passages relevant to a query."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Research query or topic"}
                    },
                    "required": ["query"],
                }
            },
        }
    },
]

SYSTEM_PROMPT = (
    "You are Quant, an AI trading copilot powered by research from leading finance textbooks "
    "(Shiller, Brealey-Myers-Allen) and real-time market data. "
    "Help the user build and refine investment strategies, explain financial concepts, "
    "and analyse their paper-trading portfolio. "
    "Always ground recommendations in evidence from the research library when relevant. "
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

    if name == "search_research":
        query = tool_input.get("query", "")
        results = search_research(query)
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
