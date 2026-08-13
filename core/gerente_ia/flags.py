"""Feature flag do Gerente IA V1."""

from core.runtime.registry import module_v1_enabled


def gerente_ia_v1_enabled() -> bool:
    """Libera o Cérebro somente quando adapters reais mínimos estiverem prontos."""

    return module_v1_enabled(
        name="gerente_ia",
        flag_env="FM_AI_GERENTE_IA_V1",
        required_adapters=("orders", "stock", "auth"),
    )
