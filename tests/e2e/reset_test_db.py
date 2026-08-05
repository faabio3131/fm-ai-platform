from __future__ import annotations

import os
import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ["FM_AI_TEST_MODE"] = "1"
os.environ["FM_AI_TEST_RESET_ON_START"] = "1"
os.environ["FM_AI_TEST_KEEP_TMP"] = "1"
os.environ["FM_AI_TEST_TMPDIR"] = os.environ.get("FM_AI_TEST_TMPDIR", str(ROOT / ".tmp" / "fm-ai-playwright"))

runpy.run_path(str(Path(__file__).with_name("init_test_db.py")), run_name="__main__")
