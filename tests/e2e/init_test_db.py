from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from test_database import initialize_database

ROOT = Path(__file__).resolve().parents[2]
TMPDIR = Path(os.environ["FM_AI_TEST_TMPDIR"]).resolve()
DB_PATH = TMPDIR / "fm_ai_test.sqlite3"
REAL_DB = ROOT / "banco_erp_local.db"

if DB_PATH.resolve() == REAL_DB.resolve():
    raise RuntimeError(f"Banco de teste resolveu para o banco real: {DB_PATH}")

TMPDIR.mkdir(parents=True, exist_ok=True)
initialize_database(DB_PATH)

required = {
    "usuarios",
    "clientes",
    "produtos",
    "insumos",
    "fichas_tecnicas",
    "vendas",
    "configuracoes_meta",
}

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
