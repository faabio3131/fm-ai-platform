"""Validate WP-031 fiscal authority freeze and execution ordering."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "web-parity"

DESIGN = DOCS / "WP031_FISCAL_V1_SYSTEM_DESIGN.md"
INVENTORY = DOCS / "KORDENA_WEB_PARITY_V1_INVENTARIO_MESTRE.md"
SEQUENCE = DOCS / "KORDENA_V1_SEQUENCIA_FINAL_EXECUCAO.md"
LEDGER = DOCS / "KORDENA_V1_STATE_LEDGER.json"

BASELINE = "b336def47ad4f5188307102203f4e04b98406014"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    design = DESIGN.read_text(encoding="utf-8")
    inventory = INVENTORY.read_text(encoding="utf-8")
    sequence = SEQUENCE.read_text(encoding="utf-8")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))

    require(BASELINE in design, "WP031 baseline fiscal V1 ausente do System Design")
    for marker in (
        "Outbound Fiscal",
        "Inbound Fiscal",
        "Fiscal Procurement",
        "Smart Fiscal Intake",
        "KordenaFiscalBridge",
        "Visual Premium final",
    ):
        require(marker in design, f"System Design WP031 incompleto: {marker}")

    require(
        "## 18. WP-031A — Fiscal V1 System Design / Authority Freeze" in inventory,
        "Inventario mestre sem registro WP-031A",
    )
    require(
        "WP-031 Fiscal completo -> Fiscal Master Gate -> Visual Premium final"
        in inventory,
        "Inventario mestre nao congela a ordem Fiscal -> Master Gate -> Premium",
    )

    require(
        "## WP-031 — sequência fiscal reconciliada em 18/09/2026" in sequence,
        "Sequencia final sem reconciliacao WP-031",
    )
    fiscal_section_pos = sequence.find(
        "## WP-031 — sequência fiscal reconciliada em 18/09/2026"
    )
    fiscal_pos = sequence.find("WP-031 Master Gate", fiscal_section_pos)
    premium_pos = sequence.find("Visual Premium final", fiscal_pos)
    require(
        fiscal_section_pos >= 0 and fiscal_pos >= 0 and premium_pos > fiscal_pos,
        "Visual Premium aparece antes do Master Gate fiscal",
    )

    wp031 = ledger["work_packages"]["WP-031"]
    require(
        wp031["state"] in {"PENDING", "CERTIFIED"},
        "WP-031 deve estar PENDING antes da implementacao ou CERTIFIED apos o Master Gate",
    )

    if wp031["state"] == "PENDING":
        require(
            "certified_sha" not in wp031,
            "WP-031 possui certified_sha antes da implementacao",
        )
    else:
        certified_sha = wp031.get("certified_sha", "")
        evidence = wp031.get("evidence", [])
        require(
            bool(certified_sha),
            "WP-031 CERTIFIED sem certified_sha",
        )
        require(
            bool(evidence),
            "WP-031 CERTIFIED sem evidencia",
        )
        require(
            "WP031_MASTER_GATE_CERTIFICATION.md" in evidence,
            "WP-031 CERTIFIED sem certificacao formal do Master Gate",
        )

    require(
        "NFCore V2" in design and "não" in design,
        "System Design deve preservar Fiscal V1 e impedir substituicao prematura pela V2",
    )

    print("WP-031A authority freeze: PASS")
    print(f"Fiscal V1 baseline: {BASELINE}")
    print(f"WP-031 ledger state: {wp031['state']}")
    print("Execution order: Fiscal Master Gate -> Visual Premium")


if __name__ == "__main__":
    main()
