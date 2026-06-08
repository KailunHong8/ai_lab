"""
LLM-based thesis and entity relationship extractor.
Calls Bedrock to parse investment documents into structured theses and
entity graph edges, then persists them to the knowledge base tables.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Document, Entity, EntityRelationship, Thesis

EXTRACTION_PROMPT = """\
You are a financial analyst extracting structured knowledge from investment research documents.

Analyze the document and extract:
1. Investment theses — one per entity with a clear stance
2. Entity relationships — supply chain, competition, and customer links mentioned

Rules:
- Separate verified FACTS (things that happened or are confirmed) from FORECASTS (predictions or opinions).
- Use ticker symbols for entities (e.g. NVDA not "Nvidia") where known; use the clearest identifier otherwise.
- Claims should be concise, self-contained statements. Include numbers where mentioned.

Return ONLY valid JSON in this exact structure:
{
  "theses": [
    {
      "entity": "NVDA",
      "theme": "AI Infrastructure",
      "stance": "bullish",
      "type": "forecast",
      "claims": [
        "Inference demand is accelerating across hyperscalers",
        "Data center revenue expected to grow 20% YoY"
      ]
    }
  ],
  "relationships": [
    {
      "from_symbol": "NVDA",
      "to_symbol": "TSMC",
      "relationship": "customer",
      "description": "NVDA relies on TSMC for advanced node GPU fabrication"
    }
  ]
}

If the document contains no clear investment theses or relationships, return {"theses": [], "relationships": []}.
"""


def _call_bedrock(content: str) -> dict[str, Any]:
    """Synchronous Bedrock call — wrapped in asyncio.to_thread by caller."""
    import boto3
    import os

    region = os.getenv("BEDROCK_REGION", "eu-west-1")
    model_id = os.getenv("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-6")
    client = boto3.client("bedrock-runtime", region_name=region)

    # Truncate very long documents to stay within context limits
    truncated = content[:12000] if len(content) > 12000 else content

    response = client.converse(
        modelId=model_id,
        system=[{"text": EXTRACTION_PROMPT}],
        messages=[{"role": "user", "content": [{"text": truncated}]}],
    )

    text = ""
    for block in response.get("output", {}).get("message", {}).get("content", []):
        if "text" in block:
            text = block["text"]
            break

    # Extract JSON — model may wrap in markdown code fences
    if "```" in text:
        start = text.find("{", text.find("```"))
        end = text.rfind("}") + 1
        text = text[start:end] if start != -1 and end > start else text

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"theses": [], "relationships": []}


async def extract_and_save(
    document_id: str,
    content: str,
    db: AsyncSession,
    provider: str = "bedrock",
    model: str | None = None,
) -> dict:
    """
    Extract theses and entity relationships from `content`, persist to DB,
    mark the document as processed. Returns extracted counts.
    """
    import asyncio

    if provider == "ollama":
        from backend.services import ollama_client
        _model = model or ollama_client.OLLAMA_DEFAULT_MODEL
        extracted = await ollama_client.extract_json(content, EXTRACTION_PROMPT, model=_model)
    else:
        extracted = await asyncio.to_thread(_call_bedrock, content)

    # Fetch source from document record
    doc_row = await db.execute(select(Document).where(Document.id == document_id))
    doc = doc_row.scalar_one_or_none()
    source = doc.source if doc else "unknown"
    doc_date = doc.date if doc else None

    thesis_count = 0
    for t in extracted.get("theses", []):
        entity = (t.get("entity") or "").upper().strip() or None
        stance = t.get("stance", "neutral").lower()
        thesis_type = t.get("type", "forecast").lower()
        if thesis_type not in ("fact", "forecast"):
            thesis_type = "forecast"
        claims = t.get("claims", [])

        thesis = Thesis(
            id=str(uuid.uuid4())[:32],
            source=source,
            theme=t.get("theme") or None,
            entity=entity,
            stance=stance,
            claims=json.dumps(claims),
            type=thesis_type,
            date=doc_date,
            document_id=document_id,
        )
        db.add(thesis)
        thesis_count += 1

        # Upsert entity record
        if entity:
            existing_entity = await db.execute(select(Entity).where(Entity.symbol == entity))
            if not existing_entity.scalar_one_or_none():
                db.add(Entity(symbol=entity))

    rel_count = 0
    for r in extracted.get("relationships", []):
        from_sym = (r.get("from_symbol") or "").upper().strip()
        to_sym = (r.get("to_symbol") or "").upper().strip()
        rel_type = (r.get("relationship") or "").lower().strip()
        if not from_sym or not to_sym or not rel_type:
            continue

        # Upsert both entities
        for sym in (from_sym, to_sym):
            existing = await db.execute(select(Entity).where(Entity.symbol == sym))
            if not existing.scalar_one_or_none():
                db.add(Entity(symbol=sym))

        db.add(EntityRelationship(
            from_symbol=from_sym,
            to_symbol=to_sym,
            rel_type=rel_type,
            description=r.get("description") or None,
        ))
        rel_count += 1

    if doc:
        doc.processed = True

    await db.commit()
    return {"theses": thesis_count, "relationships": rel_count}
