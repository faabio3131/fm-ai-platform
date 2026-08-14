"""Feature flag do KDS V1."""

from core.runtime.registry import module_v1_enabled


def kds_v1_enabled() -> bool:
    """Libera KDS somente quando pedidos, KDS e autorização reais estiverem prontos."""

    return module_v1_enabled(
        name="kds",
        flag_env="FM_AI_KDS_V1",
        required_adapters=("orders", "kds", "auth"),
    )
