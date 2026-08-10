"""Metricas de baixa cardinalidade da Central."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol


class MetricasCentral(Protocol):
    def incrementar(self, nome: str, *, tipo: str | None = None) -> None: ...
    def observar_latencia(self, segundos: float) -> None: ...


@dataclass
class MetricasCentralEmMemoria:
    contadores: Counter[tuple[str, str | None]] = field(default_factory=Counter)
    latencias: list[float] = field(default_factory=list)

    def incrementar(self, nome: str, *, tipo: str | None = None) -> None:
        self.contadores[(nome, tipo)] += 1

    def observar_latencia(self, segundos: float) -> None:
        self.latencias.append(segundos)
