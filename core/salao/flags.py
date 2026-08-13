"""Feature flag da operação de Salão V1."""

from core.runtime.registry import module_v1_enabled


def salao_v1_enabled() -> bool:
    """Libera Salão somente com pedidos, pagamentos, adapter e autorização reais."""

    return module_v1_enabled(
        name="salao",
        flag_env="FM_AI_SALAO_V1",
        required_adapters=("orders", "payments", "salao", "auth"),
    )
