"""Fitness gate for the Kordena commercial runtime readiness inventory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_commercial_runtime_readiness_inventory_matches_code() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "check_commercial_runtime_readiness_v1.py"),
            "--verify-inventory",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        completed.stdout + "\n" + completed.stderr
    )
    assert "INVENTORY_MATCH=TRUE" in completed.stdout


def test_f9_print_capability_blockers_match_manifest() -> None:
    import json

    from scripts.check_commercial_runtime_readiness_v1 import (
        CAPABILITY_BLOCKER_RULES,
        detect_code_blockers,
    )

    manifest = json.loads(
        (ROOT / "docs" / "commercial_runtime_readiness_v1.json").read_text(
            encoding="utf-8"
        )
    )
    declared = set(
        manifest["modules"]["impressao_operacional"].get("code_blockers", [])
    )
    print_blockers = {
        blocker
        for blocker in CAPABILITY_BLOCKER_RULES
        if blocker.startswith("print_") or blocker == "kds_to_print_spool_not_composed"
    }
    detected = detect_code_blockers()

    assert detected & print_blockers == declared & print_blockers
