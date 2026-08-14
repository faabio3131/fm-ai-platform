"""Feature flag canônica do Assistente de Atendimento."""

import os


def assistente_atendimento_v1_enabled() -> bool:
    habilitada = os.getenv("FM_AI_ASSISTENTE_ATENDIMENTO_V1") == "1"
    compatibilidade = os.getenv("FM_AI_MICA_V1") == "1"
    return os.getenv("FM_AI_TEST_MODE") == "1" and (habilitada or compatibilidade)
