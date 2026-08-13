"""Feature flag da interface do garçom V1."""

from core.runtime.registry import module_v1_enabled


def garcom_v1_enabled() -> bool:
    """Libera Garçom somente com adapters operacionais e autorização reais."""

    return module_v1_enabled(
        name="garcom",
        flag_env="FM_AI_GARCOM_V1",
        required_adapters=("garcom", "salao", "kds", "auth"),
    )
