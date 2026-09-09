from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_http_e_web_reutilizam_painel_executivo_existente() -> None:
    http_source = (ROOT / "http_api" / "admin_dashboard.py").read_text(
        encoding="utf-8"
    )
    application_source = (
        ROOT / "application" / "administracao_proprietario.py"
    ).read_text(encoding="utf-8")
    web_source = (
        ROOT
        / "web"
        / "src"
        / "features"
        / "backoffice"
        / "dashboard"
        / "services"
        / "dashboard-api.ts"
    ).read_text(encoding="utf-8")

    assert "AplicacaoAdministracaoProprietarioV1" in http_source
    assert ").painel_executivo(" in http_source
    assert "def painel_executivo(" in application_source
    assert "/v1/admin/painel-executivo" in web_source


def test_wp018_tem_rota_e_navegacao_governadas() -> None:
    registry = (
        ROOT / "web" / "src" / "features" / "shell" / "module-registry.ts"
    ).read_text(encoding="utf-8")
    page = ROOT / "web" / "src" / "app" / "admin" / "dashboard" / "page.tsx"

    assert page.is_file()
    assert 'href: "/admin/dashboard"' in registry
    assert 'allPermissions: ["admin.acessar", "financeiro.visualizar"]' in registry
