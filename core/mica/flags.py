"""Feature flag da Mica V1 para runtime normal e desligamento operacional."""

import os


_VALORES_ATIVOS = {"1", "true", "yes", "on"}


def mica_v1_enabled() -> bool:
    """Mantém a Mica ativa por padrão e permite desligamento explícito.

    A camada de segurança da Mica continua responsável por exigir confirmação
    explícita do carrinho, preservar idempotência e nunca promover pagamento sem
    uma fonte financeira autorizada. Definir ``FM_AI_MICA_V1=0`` desativa a UI
    imediatamente como kill switch operacional.
    """

    valor = os.getenv("FM_AI_MICA_V1")
    if valor is None:
        return True
    return valor.strip().lower() in _VALORES_ATIVOS
