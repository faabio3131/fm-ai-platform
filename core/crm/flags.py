"""Feature flag fail-closed do CRM e conversão consentida V1."""

import os


def crm_v1_enabled() -> bool:
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_CRM_V1", "0") == "1"
