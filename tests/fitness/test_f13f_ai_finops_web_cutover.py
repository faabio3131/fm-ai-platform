from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_http_ai_finops_reutiliza_read_model_e_sintese_sem_projector() -> None:
    source = (ROOT / "http_api" / "ai_finops.py").read_text(encoding="utf-8")

    assert "AIFinOpsSQLAlchemyReadModel" in source
    assert "resumir_ai_finops" in source
    assert "AIFinOpsProjector" not in source
    assert "generate_content" not in source


def test_ai_finops_tem_rota_e_navegacao_governadas() -> None:
    registry = (
        ROOT / "web" / "src" / "features" / "shell" / "module-registry.ts"
    ).read_text(encoding="utf-8")
    page = ROOT / "web" / "src" / "app" / "admin" / "ai-finops" / "page.tsx"
    service = (
        ROOT
        / "web"
        / "src"
        / "features"
        / "backoffice"
        / "ai-finops"
        / "services"
        / "ai-finops-api.ts"
    ).read_text(encoding="utf-8")

    assert page.is_file()
    assert 'href: "/admin/ai-finops"' in registry
    assert 'allPermissions: ["admin.acessar"]' in registry
    assert "/v1/ai-finops/resumo" in service
