"""Feature flag da Impressão por Setor V1."""

import os


def impressao_v1_enabled() -> bool:
    """Habilita a PR14 somente em runtime explicitamente marcado como teste."""
    return os.getenv("FM_AI_TEST_MODE") == "1" and os.getenv("FM_AI_PRINT_V1", "0") == "1"
