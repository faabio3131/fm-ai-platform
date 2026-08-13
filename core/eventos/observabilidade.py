"""Metricas operacionais portaveis, sem dependencia de fornecedor."""

from collections import Counter
from typing import Protocol

METRICAS = frozenset(
    {
        "messages_received",
        "messages_processed",
        "messages_duplicate",
        "messages_retry",
        "messages_failed",
        "messages_dlq",
        "outbox_pending",
    }
)


class MetricasEventos(Protocol):
    def incrementar(self, nome: str, quantidade: int = 1) -> None: ...
    def valor(self, nome: str) -> int: ...


class ColetorMetricasEmMemoria:
    def __init__(self) -> None:
        self._valores: Counter[str] = Counter()

    def incrementar(self, nome: str, quantidade: int = 1) -> None:
        if nome not in METRICAS:
            raise ValueError("Metrica de eventos desconhecida")
        self._valores[nome] += quantidade

    def valor(self, nome: str) -> int:
        return self._valores[nome]
