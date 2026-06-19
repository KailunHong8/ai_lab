"""
One-off backfill: read all .md files from knowledge_base/documents/,
insert Document rows into quant.db, then run thesis/entity extraction
via the existing extract_and_save() for each document.

Run from the repo root:
    python scripts/backfill_documents.py
"""
import asyncio
import hashlib
import re
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so backend imports work
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from backend.db import SessionLocal, init_db
from backend.models import Document
from backend.services import thesis_extractor

DOCS_DIR = ROOT / "knowledge_base" / "documents"
SOURCE = "ARK"


def _parse_filename(stem: str) -> tuple[str | None, str]:
    """
    '20251215_3eb669e8' -> date='2025-12-15', title=stem
    'unknown_6465482e'  -> date=None,          title=stem
    """
    m = re.match(r"^(\d{4})(\d{2})(\d{2})_", stem)
    if m:
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        date = None
    return date, stem


async def backfill():
    await init_db()

    md_files = sorted(DOCS_DIR.glob("*.md"))
    total = len(md_files)
    print(f"Found {total} .md files in {DOCS_DIR}")

    inserted = 0
    skipped = 0
    errors = 0

    for i, path in enumerate(md_files, 1):
        content = path.read_text(encoding="utf-8")
        doc_id = hashlib.sha256(content.encode()).hexdigest()[:32]
        date, title = _parse_filename(path.stem)

        async with SessionLocal() as db:
            existing = await db.execute(select(Document).where(Document.id == doc_id))
            if existing.scalar_one_or_none():
                print(f"[{i}/{total}] SKIP (duplicate)  {path.name}")
                skipped += 1
                continue

            doc = Document(
                id=doc_id,
                source=SOURCE,
                title=title,
                content=content,
                date=date,
                processed=False,
            )
            db.add(doc)
            await db.commit()

        print(f"[{i}/{total}] Inserted {path.name} — running extraction...", end=" ", flush=True)

        try:
            async with SessionLocal() as db:
                result = await thesis_extractor.extract_and_save(
                    doc_id, content, db, provider="bedrock"
                )
            print(f"theses={result['theses']} relationships={result['relationships']}")
            inserted += 1
        except Exception as exc:
            print(f"ERROR: {exc}")
            errors += 1

    print(f"\nDone. inserted={inserted} skipped={skipped} errors={errors}")


if __name__ == "__main__":
    asyncio.run(backfill())
