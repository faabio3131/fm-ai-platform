"""Compute or diagnose the current SQLite schema baseline."""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from sqlalchemy import create_engine

from migrations.history_guard import SCHEMA_ALGORITHM, schema_digest
from migrations.runner import run_migrations

OUTPUT = Path("schema-baseline-candidate.json")


def main() -> None:
    payload: dict[str, object]
    try:
        engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
        applied = run_migrations(engine)
        digest, table_count = schema_digest(engine)
        payload = {
            "success": True,
            "algorithm": SCHEMA_ALGORITHM,
            "dialect": engine.dialect.name,
            "signature_sha256": digest,
            "table_count": table_count,
            "applied_count": len(applied),
            "last_applied": applied[-1] if applied else None,
        }
    except Exception as exc:  # diagnostic probe must always emit evidence
        payload = {
            "success": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }

    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
