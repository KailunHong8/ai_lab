"""
Ollama local LLM client — backup for AWS Bedrock.
Uses the Ollama REST API at http://localhost:11434 (configurable via OLLAMA_HOST).

Default model: OLLAMA_MODEL env var, falls back to "qwen2.5:9b".
Update OLLAMA_MODEL to match whatever you pulled, e.g. "qwen3:8b".
"""
from __future__ import annotations

import json
import os
import uuid

import httpx

from backend.services.bedrock import TOOLS, SYSTEM_PROMPT, _dispatch_tool

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:9b")


def _tools_to_ollama(tools: list) -> list:
    """Bedrock toolSpec → Ollama/OpenAI function format."""
    result = []
    for t in tools:
        spec = t["toolSpec"]
        result.append({
            "type": "function",
            "function": {
                "name": spec["name"],
                "description": spec["description"],
                "parameters": spec["inputSchema"]["json"],
            },
        })
    return result


def _history_to_ollama(history: list[dict]) -> list[dict]:
    """Convert bedrock-format history to Ollama message list."""
    out: list[dict] = []
    for msg in history:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        text_parts: list[str] = []
        tool_calls: list[dict] = []
        tool_results: list[dict] = []

        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                tool_calls.append({
                    "id": tu.get("toolUseId", str(uuid.uuid4())),
                    "type": "function",
                    "function": {
                        "name": tu["name"],
                        "arguments": json.dumps(tu["input"]),
                    },
                })
            elif "toolResult" in block:
                tr = block["toolResult"]
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tr.get("toolUseId", str(uuid.uuid4())),
                    "content": (tr.get("content") or [{}])[0].get("text", ""),
                })

        if tool_results:
            out.extend(tool_results)
        elif tool_calls:
            out.append({
                "role": role,
                "content": " ".join(text_parts) or "",
                "tool_calls": tool_calls,
            })
        else:
            out.append({"role": role, "content": " ".join(text_parts)})

    return out


async def chat(
    message: str,
    history: list[dict],
    portfolio_snapshot: dict | None = None,
    model: str = OLLAMA_DEFAULT_MODEL,
) -> str:
    """
    Agentic chat turn via Ollama. Same signature as bedrock.chat.
    Reuses the same TOOLS list and _dispatch_tool from bedrock.py.
    """
    ollama_tools = _tools_to_ollama(TOOLS)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_history_to_ollama(history))
    messages.append({"role": "user", "content": message})

    async with httpx.AsyncClient(timeout=180.0) as client:
        while True:
            try:
                resp = await client.post(
                    f"{OLLAMA_HOST}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "tools": ollama_tools,
                        "stream": False,
                    },
                )
                resp.raise_for_status()
            except httpx.ConnectError:
                return "Ollama is not running. Start it with `ollama serve` and try again."
            except httpx.HTTPStatusError as exc:
                return f"Ollama error {exc.response.status_code}: {exc.response.text[:200]}"

            data = resp.json()
            assistant_msg = data.get("message", {})
            messages.append(assistant_msg)

            tool_calls = assistant_msg.get("tool_calls") or []
            if not tool_calls:
                return assistant_msg.get("content", "")

            for tc in tool_calls:
                fn = tc.get("function", {})
                try:
                    args = fn.get("arguments", {})
                    if isinstance(args, str):
                        args = json.loads(args)
                    result = await _dispatch_tool(fn["name"], args, portfolio_snapshot)
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})

                messages.append({"role": "tool", "content": result})


async def extract_json(content: str, prompt: str, model: str = OLLAMA_DEFAULT_MODEL) -> dict:
    """
    JSON extraction via Ollama — no tool use, just structured output.
    Used by thesis_extractor for document parsing.
    """
    truncated = content[:12000] if len(content) > 12000 else content

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_HOST}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": truncated},
                    ],
                    "stream": False,
                },
            )
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPStatusError):
            return {"theses": [], "relationships": []}

    text = resp.json().get("message", {}).get("content", "")

    if "```" in text:
        start = text.find("{", text.find("```"))
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"theses": [], "relationships": []}
