from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import TYPE_CHECKING

ROOT = Path(__file__).resolve().parents[2]
root_path = str(ROOT)
if root_path not in sys.path:
    sys.path.insert(0, root_path)

if TYPE_CHECKING:
    from tests.e2e.test_database import bootstrap_database, required_tables
else:
    from test_database import bootstrap_database, required_tables

TMPDIR = Path(os.environ["FM_AI_TEST_TMPDIR"]).resolve()
DB_PATH = TMPDIR / "fm_ai_test.sqlite3"
REAL_DB = ROOT / "banco_erp_local.db"

if DB_PATH.resolve() == REAL_DB.resolve():
    raise RuntimeError(f"Banco de teste resolveu para o banco real: {DB_PATH}")

TMPDIR.mkdir(parents=True, exist_ok=True)
bootstrap_database(DB_PATH)

required = required_tables()

conn = sqlite3.connect(DB_PATH)
try:
    existing = {
        row[0]
        for row in conn.execute("select name from sqlite_master where type='table'")
    }
    missing = sorted(required - existing)
    if missing:
        raise RuntimeError(f"Schema de teste incompleto; tabelas ausentes: {missing}")
finally:
    conn.close()

if not DB_PATH.exists() or DB_PATH.stat().st_size <= 0:
    raise RuntimeError(f"Banco temporário não ficou pronto: {DB_PATH}")

print(DB_PATH)
