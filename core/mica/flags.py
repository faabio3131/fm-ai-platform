"""Compatibilidade da feature flag histórica do Assistente de Atendimento."""

from core.assistente_atendimento.flags import assistente_atendimento_v1_enabled


def mica_v1_enabled() -> bool:
    """Alias legado; preserve testes/configurações antigas sem fixar identidade pública."""

    return assistente_atendimento_v1_enabled()
