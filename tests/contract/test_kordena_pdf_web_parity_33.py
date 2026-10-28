import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SURFACES = {
    "WP-001": "web/src/app/login/page.tsx",
    "WP-002": "web/src/features/auth/components/UnitSelectorModal.tsx",
    "WP-003": "web/src/features/shell/module-registry.ts",
    "WP-004": "web/src/app/page.tsx",
    "WP-005": "web/src/app/pdv/page.tsx",
    "WP-006": "web/src/app/salao/page.tsx",
    "WP-007": "web/src/app/kds/page.tsx",
    "WP-008": "web/src/app/garcom/page.tsx",
    "WP-009": "web/src/app/pedidos/page.tsx",
    "WP-010": "web/src/app/delivery/page.tsx",
    "WP-011": "web/src/app/entrega/page.tsx",
    "WP-012": "web/src/features/orders/components/MarketplaceChannelPanel.tsx",
    "WP-013": "web/src/app/catalogo/page.tsx",
    "WP-014": "web/src/features/backoffice/catalogo/components/FichaTecnicaWorkspace.tsx",
    "WP-015": "web/src/app/estoque/page.tsx",
    "WP-016": "web/src/app/admin/crm/page.tsx",
    "WP-017": "web/src/app/admin/campanhas/page.tsx",
    "WP-018": "web/src/app/admin/dashboard/page.tsx",
    "WP-019": "web/src/app/admin/ai-finops/page.tsx",
    "WP-020": "web/src/app/admin/page.tsx",
    "WP-021": "web/src/features/auth/components/AdminStepUpGuard.tsx",
    "WP-022": "web/src/app/admin/empresa/page.tsx",
    "WP-023": "web/src/app/admin/usuarios/page.tsx",
    "WP-024": "web/src/app/admin/configuracao/page.tsx",
    "WP-025": "web/src/app/admin/impressao/page.tsx",
    "WP-026": "web/src/app/admin/integracoes/page.tsx",
    "WP-027": "web/src/app/admin/assistente-atendimento/page.tsx",
    "WP-028": "web/src/app/gerente-ia/page.tsx",
    "WP-029": "web/src/app/pagamentos/page.tsx",
    "WP-030": "web/src/app/cardapio/[publicId]/[slug]/page.tsx",
    "WP-031": "web/src/app/admin/fiscal/page.tsx",
    "WP-032": "web/src/app/admin/notificacoes/page.tsx",
    "WP-033": "web/src/app/admin/auditoria/page.tsx",
}


def test_pdf_web_parity_keeps_all_33_surfaces_materialized() -> None:
    assert len(SURFACES) == 33
    missing = {
        work_package: path
        for work_package, path in SURFACES.items()
        if not (ROOT / path).is_file()
    }
    assert missing == {}


def test_all_33_pdf_work_packages_are_certified_with_evidence() -> None:
    ledger = json.loads(
        (ROOT / "docs/web-parity/KORDENA_V1_STATE_LEDGER.json").read_text()
    )
    expected = set(SURFACES)
    work_packages = ledger["work_packages"]
    assert expected.issubset(work_packages)

    invalid = {
        work_package: {
            "state": work_packages[work_package].get("state"),
            "certified_sha": work_packages[work_package].get("certified_sha"),
            "evidence": work_packages[work_package].get("evidence"),
        }
        for work_package in sorted(expected)
        if (
            work_packages[work_package].get("state") != "CERTIFIED"
            or not work_packages[work_package].get("certified_sha")
            or not work_packages[work_package].get("evidence")
        )
    }
    assert invalid == {}


def test_wp017_is_first_class_web_surface_and_not_only_crm_button() -> None:
    registry = (ROOT / "web/src/features/shell/module-registry.ts").read_text()
    frontend = (ROOT / "http_api/frontend_app.py").read_text()
    assert 'href: "/admin/campanhas"' in registry
    assert "build_campanhas_web_router" in frontend
