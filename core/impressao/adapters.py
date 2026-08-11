"""Portas de saída da Impressão por Setor V1."""

from __future__ import annotations

from typing import Protocol


class ErroAdaptadorImpressao(Exception):
    """Falha normalizada por qualquer adapter físico de impressão."""


class PortaImpressora(Protocol):
    def imprimir(self, *, impressora_id: str, job_id: str, conteudo: str) -> None: ...


class ImpressoraFake:
    """Adapter de teste: nunca toca hardware, rede ou spool do sistema operacional."""

    def __init__(self, *, falhar: bool = False) -> None:
        self.falhar = falhar
        self.impressoes: list[tuple[str, str, str]] = []

    def imprimir(self, *, impressora_id: str, job_id: str, conteudo: str) -> None:
        if self.falhar:
            raise ErroAdaptadorImpressao("impressora_indisponivel")
        self.impressoes.append((impressora_id, job_id, conteudo))
