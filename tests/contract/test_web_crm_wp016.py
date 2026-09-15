from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp016_crm_reuses_session_aware_canonical_boundary() -> None:
    router = _read("http_api/crm.py")
    canonical_app = _read("http_api/app.py")
    frontend_app = _read("http_api/frontend_app.py")
    api = _read("web/src/features/backoffice/crm/services/crm-api.ts")

    assert 'APIRouter(prefix="/v1/crm"' in router
    assert "obter_identidade_operacional" in router
    assert "Permissao.CLIENTE_VISUALIZAR" in router
    assert "Permissao.CLIENTE_EDITAR" in router
    assert "Permissao.ADMIN_ACESSAR" in router
    assert "auth_runtime.admin_status(request)" in router
    assert "seguranca.admin_step_up_exigido" in router
    assert "creditar_cashback_manual" in router
    assert "RepositorioCashbackSQLAlchemy" in router
    assert "build_crm_router" in canonical_app
    assert "app = build_http_app(settings=resolved_settings, **kwargs)" in frontend_app
    assert 'credentials: "include"' in api
    assert "/v1/crm/clientes" in api


def test_wp016_web_delegates_cashback_rules_to_canonical_backend() -> None:
    workspace = _read("web/src/features/backoffice/crm/components/CrmWorkspace.tsx")
    api = _read("web/src/features/backoffice/crm/services/crm-api.ts")
    application = _read("application/crm_cashback_comercial.py")

    assert "listarClientesCrm" in workspace
    assert "consultarCashback" in workspace
    assert "creditarCashback" in workspace
    assert "SaldoCashbackComercial" in application
    assert "ServicoCashback" in application
    assert "origem=\"ajuste_manual_governado\"" in application
    assert "idempotency_key=idempotency_key" in application
    assert "clientes.c.id == legacy_cliente_id" in application
    assert 'request("/v1/crm/clientes")' in api
    assert "/cashback/creditos`" in api
    assert '"Idempotency-Key": idempotencyKey' in api
