"""Métricas mínimas e sem PII da interface do garçom V1."""

from collections import Counter


class ColetorMetricasGarcom:
    def __init__(self) -> None:
        self._contadores: Counter[str] = Counter()

    def incrementar(self, nome: str, valor: int = 1) -> None:
        if valor < 0:
            raise ValueError("valor_metrica_invalido")
        self._contadores[nome] += valor

    def valor(self, nome: str) -> int:
        return int(self._contadores[nome])

    def snapshot(self) -> dict[str, int]:
        return dict(self._contadores)
