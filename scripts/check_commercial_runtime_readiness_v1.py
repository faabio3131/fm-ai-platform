"""Commercial Runtime Readiness gate for Kordena V1.

This script does not declare the product ready. It makes the current cutover debt
machine-readable and blocks a module from being marked COMMERCIAL_HOMOLOGATED
while known Fake/test-runtime blockers, external blockers, or required physical
evidence are still present.

Usage:
    python scripts/check_commercial_runtime_readiness_v1.py --verify-inventory
    python scripts/check_commercial_runtime_readiness_v1.py --module assistente_atendimento --require-homologated
    python scripts/check_commercial_runtime_readiness_v1.py --all-ready
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "commercial_runtime_readiness_v1.json"

# A rule is active when every required needle is present in the file.
BLOCKER_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "auth_temporary_diagnostics": (
        "infra/streamlit_app/auth_ui.py",
        ("_auth_diagnostics_enabled",),
    ),
    "assistant_delegates_to_mica": (
        "core/assistente_atendimento/ui_streamlit.py",
        ("core.mica.ui_streamlit", "render_mica_v1"),
    ),
    "cardapio_legacy_application_in_app": (
        "app.py",
        ("AplicacaoLegacyCardapioV1",),
    ),
    "pdv_forced_legacy_outside_test": (
        "core/pdv/configuracao.py",
        (
            'seguro = os.getenv("FM_AI_TEST_MODE") == "1"',
            "if not seguro or solicitado",
            "solicitado = ModoPDV.LEGACY.value",
        ),
    ),
    "pdv_legacy_adapter_in_app": (
        "app.py",
        ("LegacyPDVSQLAlchemyAdapter",),
    ),
    "estoque_legacy_application_in_app": (
        "app.py",
        ("AplicacaoLegacyEstoqueV1",),
    ),
    "crm_direct_legacy_cashback_write": (
        "app.py",
        ("c_up.saldo_cashback += valor_add_cb",),
    ),
    "crm_marketing_fake_runtime": (
        "core/crm/runtime_teste.py",
        ("class EnvioMarketingFake",),
    ),
    "financial_dashboard_reads_legacy_venda": (
        "app.py",
        ("todas_vendas = db_dash.query(Venda).all()",),
    ),
    "salao_prepares_test_schema": (
        "core/salao/ui_streamlit.py",
        ("preparar_schema_teste(engine)",),
    ),
    "salao_uses_test_context": (
        "core/salao/ui_streamlit.py",
        ("contexto_salao_teste",),
    ),
    "salao_confirms_payment_with_test_helper": (
        "core/salao/ui_streamlit.py",
        ("registrar_pagamento_confirmado_teste_v1",),
    ),
    "garcom_prepares_test_schema": (
        "core/garcom/ui_streamlit.py",
        ("preparar_schema_teste(engine)",),
    ),
    "garcom_uses_test_context": (
        "core/garcom/ui_streamlit.py",
        ("contexto_garcom_teste",),
    ),
    "entrega_uses_test_context": (
        "core/entrega/ui_streamlit.py",
        ("contexto_entrega_teste",),
    ),
    "delivery_runtime_teste": (
        "core/delivery/ui_streamlit.py",
        ("RuntimeDeliveryTeste", "runtime_teste"),
    ),
    "delivery_demo_scope": (
        "core/delivery/ui_streamlit.py",
        ('tenant_id="tenant-demo"', 'unidade_id="unidade-demo"'),
    ),
    "ifood_transport_not_composed_for_real_network": (
        "core/marketplaces/ifood_http.py",
        ("sem rede real nesta PR",),
    ),
}

GENERIC_FORBIDDEN_IF_HOMOLOGATED = (
    re.compile(r"\b[A-Za-z0-9_]*Fake\b"),
    re.compile(r"runtime_teste"),
    re.compile(r"contexto_[A-Za-z0-9_]+_teste"),
    re.compile(r"preparar_schema_teste"),
    re.compile(r"registrar_pagamento_confirmado_teste"),
    re.compile(r"tenant-demo"),
    re.compile(r"unidade-demo"),
)


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _file_text(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def detect_code_blockers() -> set[str]:
    detected: set[str] = set()
    for blocker_id, (relative_path, needles) in BLOCKER_RULES.items():
        text = _file_text(relative_path)
        if text and all(needle in text for needle in needles):
            detected.add(blocker_id)
    return detected


def _declared_code_blockers(manifest: dict[str, Any]) -> set[str]:
    declared: set[str] = set()
    for module in manifest["modules"].values():
        declared.update(module.get("code_blockers", []))
    return declared


def _verify_inventory(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    detected = detect_code_blockers()
    declared = _declared_code_blockers(manifest)

    missing_from_manifest = sorted(detected - declared)
    stale_in_manifest = sorted(declared - detected)

    if missing_from_manifest:
        errors.append(
            "Bloqueadores detectados e nao inventariados: "
            + ", ".join(missing_from_manifest)
        )
    if stale_in_manifest:
        errors.append(
            "Bloqueadores declarados que nao existem mais no codigo: "
            + ", ".join(stale_in_manifest)
            + ". Atualize o status/evidencia no mesmo checkpoint."
        )

    statuses = set(manifest.get("statuses", []))
    for module_name, module in manifest["modules"].items():
        status = module.get("status")
        if status not in statuses:
            errors.append(f"{module_name}: status invalido {status!r}")

        for blocker in module.get("code_blockers", []):
            if blocker not in BLOCKER_RULES:
                errors.append(
                    f"{module_name}: blocker desconhecido no gate: {blocker}"
                )

        if status == "COMMERCIAL_HOMOLOGATED":
            errors.extend(_validate_homologated(module_name, module))

    return errors


def _generic_forbidden_hits(module: dict[str, Any]) -> list[str]:
    hits: list[str] = []
    for relative_path in module.get("commercial_paths", []):
        text = _file_text(relative_path)
        if not text:
            hits.append(f"arquivo comercial ausente: {relative_path}")
            continue
        for pattern in GENERIC_FORBIDDEN_IF_HOMOLOGATED:
            if pattern.search(text):
                hits.append(
                    f"{relative_path}: padrao proibido em runtime homologado: "
                    f"{pattern.pattern}"
                )
    return hits


def _validate_homologated(module_name: str, module: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if module.get("code_blockers"):
        errors.append(
            f"{module_name}: COMMERCIAL_HOMOLOGATED com code_blockers ativos"
        )
    if module.get("external_blockers"):
        errors.append(
            f"{module_name}: COMMERCIAL_HOMOLOGATED com external_blockers ativos"
        )

    evidence = module.get("evidence", {})
    for key in ("sha", "commercial_runtime_e2e", "physical_test"):
        if not str(evidence.get(key) or "").strip():
            errors.append(
                f"{module_name}: COMMERCIAL_HOMOLOGATED sem evidencia obrigatoria {key}"
            )

    errors.extend(
        f"{module_name}: {hit}" for hit in _generic_forbidden_hits(module)
    )
    return errors


def _print_report(manifest: dict[str, Any]) -> None:
    print("KORDENA V1 — COMMERCIAL RUNTIME READINESS")
    for name, module in manifest["modules"].items():
        code = len(module.get("code_blockers", []))
        external = len(module.get("external_blockers", []))
        print(
            f"- {name}: {module['status']} "
            f"(code_blockers={code}, external_blockers={external})"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-inventory", action="store_true")
    parser.add_argument("--module")
    parser.add_argument("--require-homologated", action="store_true")
    parser.add_argument("--all-ready", action="store_true")
    args = parser.parse_args()

    manifest = _load_manifest()
    inventory_errors = _verify_inventory(manifest)
    if inventory_errors:
        for error in inventory_errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.verify_inventory:
        _print_report(manifest)
        print("INVENTORY_MATCH=TRUE")

    if args.module:
        module = manifest["modules"].get(args.module)
        if module is None:
            print(f"ERROR: modulo desconhecido: {args.module}", file=sys.stderr)
            return 2
        print(
            f"MODULE={args.module} STATUS={module['status']} "
            f"CODE_BLOCKERS={len(module.get('code_blockers', []))} "
            f"EXTERNAL_BLOCKERS={len(module.get('external_blockers', []))}"
        )
        if args.require_homologated:
            errors = _validate_homologated(args.module, module)
            if module["status"] != "COMMERCIAL_HOMOLOGATED":
                errors.append(
                    f"{args.module}: status atual e {module['status']}, "
                    "nao COMMERCIAL_HOMOLOGATED"
                )
            if errors:
                for error in errors:
                    print(f"NO_GO: {error}", file=sys.stderr)
                return 3
            print("COMMERCIAL_HOMOLOGATION_GATE=GREEN")

    if args.all_ready:
        errors: list[str] = []
        for name, module in manifest["modules"].items():
            if module["status"] != "COMMERCIAL_HOMOLOGATED":
                errors.append(f"{name}: {module['status']}")
            errors.extend(_validate_homologated(name, module))
        if errors:
            for error in errors:
                print(f"NO_GO: {error}", file=sys.stderr)
            return 3
        print("KORDENA_V1_COMMERCIAL_READINESS=GREEN")

    if not (args.verify_inventory or args.module or args.all_ready):
        _print_report(manifest)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
