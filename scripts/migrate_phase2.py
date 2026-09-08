"""
Migration: add Phase 2 Strategy Studio tables and FK columns.

New tables:
  strategies, strategy_versions, data_snapshots, validation_reports

New columns on simulation_runs:
  strategy_version_id, data_snapshot_id, validation_report_id

Safe to run multiple times — all operations are guarded by existence checks.

Usage:
    python scripts/migrate_phase2.py
    python scripts/migrate_phase2.py --db path/to/quant.db
"""
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).parent.parent / "quant.db"


def _existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {r[1] for r in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def migrate(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    added = 0

    # ── New tables ─────────────────────────────────────────────────────────────

    if not _table_exists(conn, "strategies"):
        conn.execute("""
            CREATE TABLE strategies (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                archived_at DATETIME
            )
        """)
        print("  strategies table created")
        added += 1

    if not _table_exists(conn, "strategy_versions"):
        conn.execute("""
            CREATE TABLE strategy_versions (
                id               TEXT PRIMARY KEY,
                strategy_id      TEXT NOT NULL REFERENCES strategies(id),
                version_number   INTEGER NOT NULL,
                definition_json  TEXT NOT NULL,
                definition_hash  TEXT,
                status           TEXT NOT NULL DEFAULT 'draft',
                source_prompt    TEXT,
                parser_output_json TEXT,
                user_edits_json  TEXT,
                compiled_plan_json TEXT,
                schema_version   INTEGER NOT NULL DEFAULT 1,
                reviewed_at      DATETIME,
                created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sv_strategy_id ON strategy_versions(strategy_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sv_hash ON strategy_versions(definition_hash)")
        print("  strategy_versions table created")
        added += 1

    if not _table_exists(conn, "data_snapshots"):
        conn.execute("""
            CREATE TABLE data_snapshots (
                id           TEXT PRIMARY KEY,
                symbols_json TEXT NOT NULL,
                start_date   TEXT NOT NULL,
                end_date     TEXT NOT NULL,
                source       TEXT NOT NULL,
                row_count    INTEGER NOT NULL DEFAULT 0,
                manifest_json TEXT,
                content_hash TEXT,
                created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  data_snapshots table created")
        added += 1

    if not _table_exists(conn, "validation_reports"):
        conn.execute("""
            CREATE TABLE validation_reports (
                id                   TEXT PRIMARY KEY,
                strategy_version_id  TEXT NOT NULL REFERENCES strategy_versions(id),
                data_snapshot_id     TEXT NOT NULL REFERENCES data_snapshots(id),
                fold_results_json    TEXT,
                holdout_json         TEXT,
                bootstrap_json       TEXT,
                regime_json          TEXT,
                summary_json         TEXT NOT NULL,
                gate_results_json    TEXT,
                status               TEXT NOT NULL DEFAULT 'pending',
                created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vr_sv_id ON validation_reports(strategy_version_id)")
        print("  validation_reports table created")
        added += 1

    # ── New columns on simulation_runs ─────────────────────────────────────────

    sim_cols = _existing_columns(conn, "simulation_runs")
    sim_additions = [
        ("strategy_version_id", "TEXT"),
        ("data_snapshot_id",    "TEXT"),
        ("validation_report_id","TEXT"),
    ]
    for col, col_type in sim_additions:
        if col not in sim_cols:
            conn.execute(f"ALTER TABLE simulation_runs ADD COLUMN {col} {col_type}")
            print(f"  simulation_runs.{col} added")
            added += 1

    conn.commit()
    conn.close()
    print(f"\nDone. {added} object(s) created/altered.")


if __name__ == "__main__":
    db_path = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--db" else DEFAULT_DB
    if not db_path.exists():
        print(f"DB not found: {db_path}")
        sys.exit(1)
    print(f"Migrating {db_path} …")
    migrate(db_path)
