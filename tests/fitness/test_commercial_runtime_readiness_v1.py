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


def test_f9_print_missing_capabilities_are_detected() -> None:
    from scripts.check_commercial_runtime_readiness_v1 import detect_code_blockers

    detected = detect_code_blockers()
    assert {
        "print_commercial_composition_missing",
        "kds_to_print_spool_not_composed",
        "print_real_adapter_not_composed",
        "print_destinations_not_commercially_configured",
        "print_surface_not_exposed_in_app",
    } <= detected
