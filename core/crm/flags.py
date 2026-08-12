"""Feature flag do CRM e conversão consentida V1."""

from core.runtime.registry import module_v1_enabled


def crm_v1_enabled() -> bool:
    """Libera CRM V1 somente com persistência/transporte e autorização reais."""

    return module_v1_enabled(
        name="crm",
        flag_env="FM_AI_CRM_V1",
        required_adapters=("crm", "auth"),
    )
