"""Fitness gate for F11-G Delivery Próprio readiness closure."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "docs" / "commercial_runtime_readiness_v1.json"
CLOSURE = ROOT / "docs" / "inventario-fase11-delivery-proprio-cutover-v1-fechamento.md"

F11F_SHA = "ee33c165730fb9a5e934dbaccdde009bfac059a9"
F11F_E2E = (
    "github-actions://Fase-11F-Delivery-Commercial-Runtime-E2E-Gate/"
    "run-8/33987132464"
)
F11F_BROWSER = (
    "github-actions://Fase-11F-Delivery-Commercial-Runtime-E2E-Gate/"
    "run-8/desktop-chromium"
)


def _delivery_readiness() -> dict[str, object]:
    manifest = json.loads(READINESS.read_text(encoding="utf-8"))
    return manifest["modules"]["delivery_proprio"]


def test_f11g_delivery_readiness_matches_proven_f11f_candidate() -> None:
    delivery = _delivery_readiness()

    assert delivery["status"] == "COMMERCIAL_CANDIDATE"
    assert delivery["code_blockers"] == []
    assert delivery["external_blockers"] == []
    assert delivery["evidence"] == {
        "sha": F11F_SHA,
        "commercial_runtime_e2e": F11F_E2E,
        "physical_test": F11F_BROWSER,
    }


def test_f11g_does_not_reintroduce_retired_delivery_blockers() -> None:
    delivery = _delivery_readiness()
    serialized = json.dumps(delivery, ensure_ascii=False)

    assert "delivery_runtime_teste" not in serialized
    assert "delivery_demo_scope" not in serialized


def test_f11g_closure_preserves_governance_and_no_deploy_claim() -> None:
    text = CLOSURE.read_text(encoding="utf-8")

    assert F11F_SHA in text
    assert "17/17 workflows SUCCESS" in text
    assert "5/5 workflows SUCCESS" in text
    assert "COMMERCIAL_CANDIDATE" in text
    assert "Nenhum deploy é autorizado ou executado" in text
    assert "COMMERCIAL_HOMOLOGATED" in text
