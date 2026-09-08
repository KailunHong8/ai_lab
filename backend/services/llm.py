"""Simple LLM completion helper for the multi-agent pipeline (no tool use)."""
from __future__ import annotations

import asyncio
import functools
import json
import os
import re


async def complete(
    system: str,
    user: str,
    provider: str = "bedrock",
    model: str | None = None,
) -> str:
    """Single completion (no tool use). Returns the assistant text."""
    if provider == "bedrock":
        return await _bedrock_complete(system, user, model)
    elif provider in ("ollama", "ollama-cloud"):
        return await _ollama_complete(system, user, provider, model)
    else:
        return await _bedrock_complete(system, user, model)


async def _bedrock_complete(system: str, user: str, model: str | None) -> str:
    import boto3
    from botocore.config import Config

    region = os.getenv("BEDROCK_REGION", "eu-west-1")
    model_id = model or os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
    aws_profile = os.getenv("AWS_PROFILE") or None

    def _call():
        session = boto3.Session(profile_name=aws_profile)
        client = session.client("bedrock-runtime", region_name=region, config=Config(read_timeout=300))
        resp = client.converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
        )
        return resp["output"]["message"]["content"][0]["text"]

    return await asyncio.to_thread(_call)


async def _ollama_complete(system: str, user: str, provider: str, model: str | None) -> str:
    import httpx

    if provider == "ollama-cloud":
        host = "https://ollama.com"
        api_key = os.getenv("OLLAMA_API_KEY", "")
        default_model = os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b")
    else:
        host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        api_key = ""
        default_model = os.getenv("OLLAMA_MODEL", "qwen2.5:9b")

    _model = model or default_model
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{host}/api/chat/completions",
            headers=headers,
            json={
                "model": _model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response string."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extract first {...} block
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}
