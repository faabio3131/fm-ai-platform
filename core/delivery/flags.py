"""Feature flag do Delivery Próprio V1."""

from core.runtime.registry import module_v1_enabled


def delivery_v1_enabled() -> bool:
    """Libera Delivery somente com pedidos, pagamentos, entrega e autorização reais."""

    return module_v1_enabled(
        name="delivery",
        flag_env="FM_AI_DELIVERY_V1",
        required_adapters=("orders", "payments", "delivery", "auth"),
    )
