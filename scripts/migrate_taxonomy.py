"""
Migration: add taxonomy columns to documents and theses tables.

Safe to run multiple times — each ALTER TABLE is guarded by a column-existence check.

Usage:
    python scripts/migrate_taxonomy.py
    python scripts/migrate_taxonomy.py --db path/to/quant.db
"""
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "quant.db"


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")

    doc_cols = _existing_columns(conn, "documents")
    thesis_cols = _existing_columns(conn, "theses")

    doc_additions = [
        ("corpus",           "TEXT"),
        ("source_type",      "TEXT"),
        ("fund",             "TEXT"),
        ("channel",          "TEXT"),
        ("reliability_tier", "INTEGER"),
        ("published_at",     "TEXT"),
        ("ingested_at",      "DATETIME"),
        ("recency_flag",     "TEXT DEFAULT 'timely'"),
        ("expiration_at",    "DATETIME"),
        ("citations_json",   "TEXT"),
        ("ingestion_job_id", "TEXT"),
    ]

    thesis_additions = [
        ("source_type",      "TEXT"),
        ("fund",             "TEXT"),
        ("reliability_tier", "INTEGER"),
        ("recency_flag",     "TEXT"),
        ("expiration_at",    "DATETIME"),
    ]

    added = 0
    for col, col_type in doc_additions:
        if col not in doc_cols:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {col_type}")
            print(f"  documents.{col} added")
            added += 1

    for col, col_type in thesis_additions:
        if col not in thesis_cols:
            conn.execute(f"ALTER TABLE theses ADD COLUMN {col} {col_type}")
            print(f"  theses.{col} added")
            added += 1

    # Back-fill corpus for existing documents based on source heuristic:
    # anything that looks like a fund letter → market_opinion; everything else → principles
    conn.execute("""
        UPDATE documents
        SET corpus = CASE
            WHEN upper(source) IN ('ARK','GMO','SEQUOIA','BRIDGEWATER') THEN 'market_opinion'
            ELSE 'principles'
        END
        WHERE corpus IS NULL
    """)
    conn.execute("""
        UPDATE documents
        SET source_type = CASE
            WHEN upper(source) IN ('ARK','GMO','SEQUOIA','BRIDGEWATER') THEN 'fund_letter'
            ELSE 'principle_text'
        END
        WHERE source_type IS NULL
    """)
    conn.execute("""
        UPDATE documents
        SET fund = source
        WHERE source_type = 'fund_letter' AND fund IS NULL
    """)
    conn.execute("""
        UPDATE documents
        SET reliability_tier = CASE source_type
            WHEN 'principle_text'  THEN 1
            WHEN 'fund_letter'     THEN 2
            WHEN 'user_synthesis'  THEN 3
            WHEN 'web_research'    THEN 4
            ELSE 4
        END
        WHERE reliability_tier IS NULL
    """)
    conn.execute("""
        UPDATE documents
        SET recency_flag = CASE source_type
            WHEN 'principle_text' THEN 'evergreen'
            ELSE 'timely'
        END
        WHERE recency_flag IS NULL
    """)

    # Mirror taxonomy to theses
    conn.execute("""
        UPDATE theses
        SET source_type = (SELECT source_type FROM documents WHERE documents.id = theses.document_id),
            fund        = (SELECT fund        FROM documents WHERE documents.id = theses.document_id),
            reliability_tier = (SELECT reliability_tier FROM documents WHERE documents.id = theses.document_id),
            recency_flag = (SELECT recency_flag FROM documents WHERE documents.id = theses.document_id),
            expiration_at = (SELECT expiration_at FROM documents WHERE documents.id = theses.document_id)
        WHERE document_id IS NOT NULL
    """)

    conn.commit()
    conn.close()
    print(f"\nDone. {added} column(s) added, back-fill complete.")


if __name__ == "__main__":
    db_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--db" else DEFAULT_DB
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)
    print(f"Migrating {db_path} …")
    migrate(db_path)
