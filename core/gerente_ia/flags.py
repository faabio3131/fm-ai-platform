"""Feature flag fail-closed do Gerente IA V1."""

import os


def gerente_ia_v1_enabled() -> bool:
    return (
        os.getenv("FM_AI_TEST_MODE") == "1"
        and os.getenv("FM_AI_GERENTE_IA_V1", "0") == "1"
    )
