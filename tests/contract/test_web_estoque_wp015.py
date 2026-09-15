from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp015_estoque_reuses_session_aware_canonical_boundary() -> None:
    router = _read("http_api/estoque.py")
    canonical_app = _read("http_api/app.py")
    frontend_app = _read("http_api/frontend_app.py")
    api = _read("web/src/features/backoffice/estoque/services/estoque-api.ts")

    assert 'APIRouter(prefix="/v1/estoque"' in router
    assert "obter_identidade_operacional" in router
    assert "Permissao.ESTOQUE_VISUALIZAR" in router
    assert "Permissao.ESTOQUE_AJUSTAR" in router
    assert "Permissao.ADMIN_ACESSAR" in router
    assert "auth_runtime.admin_status(request)" in router
    assert "seguranca.admin_step_up_exigido" in router
    assert "build_estoque_router" in canonical_app
    assert "app = build_http_app(settings=resolved_settings, **kwargs)" in frontend_app
    assert 'credentials: "include"' in api
    assert "/v1/estoque" in api


def test_wp015_web_delegates_stock_rules_to_http_application_boundary() -> None:
    workspace = _read(
        "web/src/features/backoffice/estoque/components/EstoqueWorkspace.tsx"
    )
    api = _read("web/src/features/backoffice/estoque/services/estoque-api.ts")
    application = _read("application/legacy_estoque_transacoes.py")

    assert "listarEstoque" in workspace
    assert "criarInsumo" in workspace
    assert "aplicarLeituraEstoque" in workspace
    assert "executarForecastingAlertas" in workspace
    assert "aplicarLeituraVisualEstoque" in workspace
    assert "excluirInsumo" in workspace
    assert "AplicacaoLegacyEstoqueV1" in application
    assert 'request("/v1/estoque/insumos"' in api
    assert 'request("/v1/estoque/leituras"' in api
    assert 'request("/v1/estoque/forecasting-alertas"' in api
    assert 'request("/v1/estoque/leituras-visuais"' in api
