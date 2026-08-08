"""Infraestrutura pura de eventos operacionais V1."""

from .erros import *  # noqa: F403
from .modelos import *  # noqa: F403
from .observabilidade import ColetorMetricasEmMemoria, MetricasEventos
from .processador import ProcessadorMensagens, RegistroHandlers
from .repositorios import (
    RepositorioDLQEmMemoria,
    RepositorioInboxEmMemoria,
    RepositorioOutboxEmMemoria,
    StatusOutbox,
)
from .retry import ErroNaoRetryable, PoliticaRetry

__all__ = [
    "ColetorMetricasEmMemoria",
    "MetricasEventos",
    "ProcessadorMensagens",
    "RegistroHandlers",
    "RepositorioDLQEmMemoria",
    "RepositorioInboxEmMemoria",
    "RepositorioOutboxEmMemoria",
    "StatusOutbox",
    "ErroNaoRetryable",
    "PoliticaRetry",
]
