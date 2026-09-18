"""Compute the current SQLite schema baseline after all official migrations."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine

from migrations.history_guard import SCHEMA_ALGORITHM, schema_digest
from migrations.runner import run_migrations

OUTPUT = Path("schema-baseline-candidate.json")


def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    digest, table_count = schema_digest(engine)
    payload = {
        "algorithm": SCHEMA_ALGORITHM,
        "dialect": engine.dialect.name,
        "signature_sha256": digest,
        "table_count": table_count,
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
