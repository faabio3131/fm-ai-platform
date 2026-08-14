"""Infraestrutura pura de eventos operacionais V1."""

from .erros import *
from .modelos import *
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
    "ErroNaoRetryable",
    "MetricasEventos",
    "PoliticaRetry",
    "ProcessadorMensagens",
    "RegistroHandlers",
    "RepositorioDLQEmMemoria",
    "RepositorioInboxEmMemoria",
    "RepositorioOutboxEmMemoria",
    "StatusOutbox",
]
