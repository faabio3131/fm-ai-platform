"""Feature flag canônica do Assistente de Atendimento."""

import os


def assistente_atendimento_v1_enabled() -> bool:
    """Habilita o Assistente V1 quando a flag oficial estiver ativa.

    A compatibilidade legada ``FM_AI_MICA_V1`` permanece restrita ao ambiente de
    teste. A flag oficial ``FM_AI_ASSISTENTE_ATENDIMENTO_V1=1`` funciona também no
    runtime normal/comercial, pois o fluxo V1 já aplica as proteções próprias do
    Assistente de Atendimento.
    """

    habilitada = os.getenv("FM_AI_ASSISTENTE_ATENDIMENTO_V1") == "1"
    compatibilidade = os.getenv("FM_AI_MICA_V1") == "1"
    modo_teste = os.getenv("FM_AI_TEST_MODE") == "1"
    return habilitada or (modo_teste and compatibilidade)
