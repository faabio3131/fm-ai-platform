"""Feature flag da Mica V1: executável somente no runtime isolado de teste."""

import os


def mica_v1_enabled() -> bool:
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_MICA_V1") == "1"
