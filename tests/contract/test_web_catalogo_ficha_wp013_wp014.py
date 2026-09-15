from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp013_catalogo_reuses_session_aware_canonical_http_boundary() -> None:
    router = _read("http_api/catalogo.py")
    canonical_app = _read("http_api/app.py")
    frontend_app = _read("http_api/frontend_app.py")
    api = _read("web/src/features/backoffice/catalogo/services/catalogo-api.ts")

    assert 'APIRouter(prefix="/v1/catalogo"' in router
    assert "auth_runtime.resolver_identidade(request)" in router
    assert "Permissao.ADMIN_ACESSAR" in router
    assert "auth_runtime.admin_status(request)" in router
    assert "seguranca.admin_step_up_exigido" in router
    assert "build_catalogo_router" in canonical_app
    assert "app = build_http_app(settings=resolved_settings, **kwargs)" in frontend_app
    assert 'credentials: "include"' in api
    assert "/v1/catalogo" in api


def test_wp014_ficha_uses_explicit_suggested_price_application() -> None:
    workspace = _read(
        "web/src/features/backoffice/catalogo/components/FichaTecnicaWorkspace.tsx"
    )

    assert "function aplicarPrecoSugerido()" in workspace
    assert "setPreco(Number(sugestao.toFixed(2)))" in workspace
    assert "Aplicar preço sugerido" in workspace
    assert "onClick={aplicarPrecoSugerido}" in workspace
    assert "if (preco === 0)" not in workspace


def test_wp014_ficha_keeps_manual_final_price_and_canonical_persistence() -> None:
    workspace = _read(
        "web/src/features/backoffice/catalogo/components/FichaTecnicaWorkspace.tsx"
    )
    application = _read("application/legacy_cardapio_transacoes.py")

    assert "Preço final (R$)" in workspace
    assert "onChange={(event) => setPreco(Number(event.target.value))}" in workspace
    assert "criarPratoComFicha" in workspace
    assert "salvar_prato_com_ficha" in application
