"""Feature flag da Expedição e Entrega V1."""

from core.runtime.registry import module_v1_enabled


def entrega_v1_enabled() -> bool:
    """Libera expedição somente com pedidos/logística/autorização reais."""

    return module_v1_enabled(
        name="entrega",
        flag_env="FM_AI_ENTREGA_V1",
        required_adapters=("orders", "delivery", "entrega", "auth"),
    )
