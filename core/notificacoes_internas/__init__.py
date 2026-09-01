"""Autoridade canônica de destinatários de notificações internas."""

from .modelos import CanalNotificacaoInterna, DestinatarioNotificacaoInterna
from .servicos import ServicoNotificacoesInternas

__all__ = [
    "CanalNotificacaoInterna",
    "DestinatarioNotificacaoInterna",
    "ServicoNotificacoesInternas",
]
