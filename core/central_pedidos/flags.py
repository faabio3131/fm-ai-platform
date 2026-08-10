"""Feature flag server-side e desligada por padrao."""

import os


def order_center_v1_enabled() -> bool:
    """Somente testes isolados podem ativar a Central nesta entrega."""
    return (
        os.getenv("FM_AI_TEST_MODE") == "1"
        and os.getenv("FM_AI_ORDER_CENTER_V1", "0") == "1"
    )
