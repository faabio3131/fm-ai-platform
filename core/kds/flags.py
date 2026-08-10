"""Feature flag do KDS V1, fail-closed e restrita ao modo de teste nesta PR."""

import os


def kds_v1_enabled() -> bool:
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_KDS_V1", "0") == "1"
