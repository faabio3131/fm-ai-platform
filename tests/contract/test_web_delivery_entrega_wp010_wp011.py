from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_wp010_delivery_has_session_aware_thin_http_boundary() -> None:
    router = _read("http_api/delivery.py")
    frontend_app = _read("http_api/frontend_app.py")

    assert 'APIRouter(prefix="/v1/delivery"' in router
    assert "obter_identidade_operacional" in router
    assert "listar_clientes_delivery_comercial" in router
    assert "confirmar_delivery_comercial" in router
    assert "cancelar_delivery_comercial" in router
    assert "Idempotency-Key".casefold() in router.casefold()
    assert "build_delivery_router" in frontend_app
    assert "tenant_id:" not in router
    assert "unidade_id:" not in router


def test_wp010_delivery_has_next_route_and_cookie_client() -> None:
    page = _read("web/src/app/delivery/page.tsx")
    workspace = _read("web/src/features/delivery/components/DeliveryWorkspace.tsx")
    api = _read("web/src/features/delivery/services/delivery-api.ts")

    assert "DeliveryWorkspace" in page
    assert "Delivery Próprio" in workspace
    assert 'credentials: "include"' in api
    assert "/v1/delivery" in api
    assert "confirmDeliveryOrder" in workspace
    assert "cancelDeliveryOrder" in workspace
    assert "tenant" not in api.casefold()
    assert "unidade" not in api.casefold()


def test_wp011_entrega_has_session_aware_http_and_canonical_application() -> None:
    router = _read("http_api/entrega.py")
    frontend_app = _read("http_api/frontend_app.py")

    assert 'APIRouter(prefix="/v1/entregas"' in router
    assert "obter_identidade_operacional" in router
    assert "ServicoEntrega" in router
    assert "AplicacaoEntregaV1" in router
    assert "listar_entregadores_elegiveis" in router
    assert "atribuir_entregador_governado" in router
    assert "Idempotency-Key".casefold() in router.casefold()
    assert "build_entrega_router" in frontend_app


def test_wp011_entrega_has_next_route_and_canonical_permission() -> None:
    page = _read("web/src/app/entrega/page.tsx")
    workspace = _read("web/src/features/entrega/components/EntregaWorkspace.tsx")
    api = _read("web/src/features/entrega/services/entrega-api.ts")
    registry = _read("web/src/features/shell/module-registry.ts")

    assert "EntregaWorkspace" in page
    assert "Expedição e Entrega" in workspace
    assert 'DELIVERY_PERMISSION = "expedicao.operar"' in workspace
    assert 'credentials: "include"' in api
    assert "/v1/entregas" in api
    assert 'id: "entrega"' in registry
    assert 'allPermissions: ["expedicao.operar"]' in registry


def test_wp010_shell_exposes_delivery_without_fake_permission_ids() -> None:
    registry = _read("web/src/features/shell/module-registry.ts")

    assert 'id: "delivery"' in registry
    assert 'href: "/delivery"' in registry
    assert 'allPermissions: ["cliente.visualizar", "pedido.visualizar"]' in registry
    assert "delivery.visualizar" not in registry
    assert "delivery.despachar" not in registry
    assert "entrega.atribuir" not in registry
    assert "WP-" not in registry
