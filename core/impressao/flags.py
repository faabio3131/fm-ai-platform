"""Feature flag da Impressão por Setor V1."""

from core.runtime.registry import module_v1_enabled


def impressao_v1_enabled() -> bool:
    """Libera impressão somente com pedido e spool/adapter reais configurados."""

    return module_v1_enabled(
        name="impressao",
        flag_env="FM_AI_PRINT_V1",
        required_adapters=("orders", "print"),
    )
