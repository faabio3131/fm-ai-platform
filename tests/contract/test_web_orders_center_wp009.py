from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp009_has_session_aware_http_boundary() -> None:
    router = _read("http_api/central_pedidos.py")
    frontend_app = _read("http_api/frontend_app.py")

    assert 'APIRouter(prefix="/v1/pedidos"' in router
    assert "obter_identidade_operacional" in router
    assert "CentralPedidosSQLAlchemy" in router
    assert "AplicacaoCentralPedidosTransacoesV1" in router
    assert "Idempotency-Key".casefold() in router.casefold()
    assert "build_central_pedidos_router" in frontend_app


def test_wp009_has_next_route_and_canonical_client() -> None:
    page = _read("web/src/app/pedidos/page.tsx")
    workspace = _read("web/src/features/orders/components/OrdersCenterWorkspace.tsx")
    api = _read("web/src/features/orders/services/orders-api.ts")

    assert "OrdersCenterWorkspace" in page
    assert "Central de Pedidos" in workspace
    assert "credentials: \"include\"" in api
    assert "/v1/pedidos" in api
    assert "sendOrderToConfirmation" in workspace
    assert "cancelOrder" in workspace


def test_wp009_web_actions_follow_canonical_rbac() -> None:
    workspace = _read("web/src/features/orders/components/OrdersCenterWorkspace.tsx")

    assert 'ALTER_ORDER_PERMISSION = "pedido.alterar"' in workspace
    assert 'CANCEL_ORDER_PERMISSION = "pedido.cancelar"' in workspace
    assert "canAlterOrder" in workspace
    assert "canCancelOrder" in workspace


def test_wp009_shell_exposes_module_only_with_pedido_visualizar() -> None:
    registry = _read("web/src/features/shell/module-registry.ts")
    assert 'id: "pedidos"' in registry
    assert 'href: "/pedidos"' in registry
    assert '"pedido.visualizar"' in registry
    assert "WP-" not in registry
