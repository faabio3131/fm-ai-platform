"""Feature flag test-only da operacao de salao V1."""

import os


def salao_v1_enabled() -> bool:
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_SALAO_V1", "0") == "1"
