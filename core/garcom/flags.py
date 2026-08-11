"""Feature flag da interface do garçom V1."""

import os


def garcom_v1_enabled() -> bool:
    """Habilita a PR12 somente no runtime explicitamente marcado como teste."""
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_GARCOM_V1", "0") == "1"
