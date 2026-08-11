"""Feature flag do Delivery Próprio V1."""

import os


def delivery_v1_enabled() -> bool:
    """Habilita PR16 somente em runtime explicitamente marcado como teste."""
    return (
        os.getenv("FM_AI_TEST_MODE") == "1"
        and os.getenv("FM_AI_DELIVERY_V1", "0") == "1"
    )
