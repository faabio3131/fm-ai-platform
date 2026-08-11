"""Feature flag da Expedição e Entrega V1."""

import os


def entrega_v1_enabled() -> bool:
    """Habilita a PR13 somente no runtime explicitamente marcado como teste."""
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_ENTREGA_V1", "0") == "1"
