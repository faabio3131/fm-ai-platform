from __future__ import annotations

import os
from pathlib import Path

from test_database import reset_database_in_place

ROOT = Path(__file__).resolve().parents[2]
os.environ["FM_AI_TEST_MODE"] = "1"
os.environ["FM_AI_TEST_RESET_ON_START"] = "1"
os.environ["FM_AI_TEST_KEEP_TMP"] = "1"
os.environ["FM_AI_TEST_TMPDIR"] = os.environ.get(
    "FM_AI_TEST_TMPDIR", str(ROOT / ".tmp" / "fm-ai-playwright")
)

db_path = Path(os.environ["FM_AI_TEST_TMPDIR"]).resolve() / "fm_ai_test.sqlite3"
real_db = ROOT / "banco_erp_local.db"
if db_path.resolve() == real_db.resolve():
    raise RuntimeError(f"Banco de teste resolveu para o banco real: {db_path}")

reset_database_in_place(db_path)
print(db_path)
