"""Feature flag da Central de Pedidos V1."""

from core.runtime.registry import module_v1_enabled


def order_center_v1_enabled() -> bool:
    """Libera a Central somente com pedidos/autorização reais no runtime normal."""

    return module_v1_enabled(
        name="central_pedidos",
        flag_env="FM_AI_ORDER_CENTER_V1",
        required_adapters=("orders", "auth"),
    )
