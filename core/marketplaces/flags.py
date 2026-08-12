"""Feature flags dos adapters de marketplace.

No modo E2E preservamos o comportamento das flags isoladas. Em runtime normal,
a camada só é liberada quando pedidos/autorização e o adapter real da plataforma
foram explicitamente configurados.
"""

from core.runtime.registry import module_v1_enabled


def marketplace_v1_enabled() -> bool:
    return module_v1_enabled(
        name="marketplaces",
        flag_env="FM_AI_MARKETPLACE_V1",
        required_adapters=("orders", "auth"),
    )


def _plataforma_habilitada(flag_env: str, adapter: str) -> bool:
    if not marketplace_v1_enabled():
        return False
    return module_v1_enabled(
        name=f"marketplace_{adapter}",
        flag_env=flag_env,
        required_adapters=(adapter,),
    )


def ifood_adapter_v1_enabled() -> bool:
    return _plataforma_habilitada("FM_AI_IFOOD_ADAPTER_V1", "ifood")


def food99_adapter_v1_enabled() -> bool:
    return _plataforma_habilitada("FM_AI_99FOOD_ADAPTER_V1", "99food")


def keeta_adapter_v1_enabled() -> bool:
    return _plataforma_habilitada("FM_AI_KEETA_ADAPTER_V1", "keeta")
