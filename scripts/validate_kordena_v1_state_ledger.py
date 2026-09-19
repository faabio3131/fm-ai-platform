from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "docs/web-parity/KORDENA_V1_STATE_LEDGER.json"
INVENTORY_PATH = ROOT / "docs/web-parity/KORDENA_WEB_PARITY_V1_INVENTARIO_MESTRE.md"
CHECKLIST_PATH = ROOT / "docs/web-parity/KORDENA_WEB_PARITY_V1_CHECKLIST_OPERACIONAL.md"

ALLOWED_STATES = {"PENDING", "IMPLEMENTED_UNCERTIFIED", "CERTIFIED", "BLOCKED"}
WP_RE = re.compile(r"^WP-\d{3}$")


def fail(message: str) -> None:
    print(f"STATE LEDGER ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    packages = ledger.get("work_packages", {})

    expected = {f"WP-{number:03d}" for number in range(1, 34)}
    actual = set(packages)
    if actual != expected:
        fail(f"WP set mismatch. missing={sorted(expected-actual)} extra={sorted(actual-expected)}")

    for wp, entry in packages.items():
        if not WP_RE.match(wp):
            fail(f"invalid WP id: {wp}")
        state = entry.get("state")
        if state not in ALLOWED_STATES:
            fail(f"{wp} has invalid state {state!r}")
        if state == "CERTIFIED" and not entry.get("evidence") and not entry.get("certified_sha"):
            fail(f"{wp} is CERTIFIED without evidence")
        if state in {"PENDING", "IMPLEMENTED_UNCERTIFIED", "BLOCKED"} and not entry.get("reason"):
            fail(f"{wp} state {state} requires a reason")

    # Narrative documents are evidence/history, never authority.  Still reject the
    # dangerous contradiction that previously caused rework: a ledger-certified WP
    # being presented by the operational checklist as PENDING/UNCERTIFIED.
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")
    for wp, entry in packages.items():
        if entry["state"] != "CERTIFIED":
            continue
        matching_lines = [line for line in checklist.splitlines() if line.startswith(f"| {wp} ")]
        for line in matching_lines:
            if "| PENDENTE |" in line or "AGUARDA CERTIFICAÇÃO" in line:
                fail(f"{wp} is CERTIFIED in ledger but checklist still presents it as pending/uncertified")

    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    if "DOCUMENTO MESTRE DE EXECUÇÃO" not in inventory:
        fail("master inventory identity missing")

    print("Kordena V1 State Ledger: VALID")
    print(f"Work packages: {len(packages)}")
    print("State authority: docs/web-parity/KORDENA_V1_STATE_LEDGER.json")


if __name__ == "__main__":
    main()
