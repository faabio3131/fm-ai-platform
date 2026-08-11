"""Feature flags fail-closed dos adapters de marketplace."""

import os


def _habilitada(nome: str) -> bool:
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv(nome, "0") == "1"


def marketplace_v1_enabled() -> bool:
    return _habilitada("FM_AI_MARKETPLACE_V1")


def ifood_adapter_v1_enabled() -> bool:
    return marketplace_v1_enabled() and _habilitada("FM_AI_IFOOD_ADAPTER_V1")


def food99_adapter_v1_enabled() -> bool:
    return marketplace_v1_enabled() and _habilitada("FM_AI_99FOOD_ADAPTER_V1")


def keeta_adapter_v1_enabled() -> bool:
    return marketplace_v1_enabled() and _habilitada("FM_AI_KEETA_ADAPTER_V1")
