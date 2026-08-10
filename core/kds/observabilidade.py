"""Metricas in-memory do KDS V1; backend persistente fica para hardening."""

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class ColetorMetricasKDS:
    contadores: Counter[str] = field(default_factory=Counter)

    def incrementar(self, nome: str, quantidade: int = 1) -> None:
        self.contadores[nome] += quantidade

    def valor(self, nome: str) -> int:
        return self.contadores[nome]
