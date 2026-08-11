"""Feature flag fail-closed do framework Marketplace V1."""

import os


def marketplace_v1_enabled() -> bool:
    return (
        os.getenv("FM_AI_TEST_MODE") == "1"
        and os.getenv("FM_AI_MARKETPLACE_V1", "0") == "1"
    )
