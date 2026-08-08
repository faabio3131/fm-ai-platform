"""Portas transacionais: core nao conhece modelos SQLAlchemy legados do app."""

from contextlib import AbstractContextManager
from typing import Protocol

from .modelos import EntradaPDV, ResultadoPDV


class ExecutorLegado(Protocol):
    def executar(self, entrada: EntradaPDV) -> ResultadoPDV: ...


class EscritorShadow(Protocol):
    def escrever(self, entrada: EntradaPDV, venda_legada_id: str | None) -> str: ...


class ExecutorAutoritativo(Protocol):
    def executar(self, entrada: EntradaPDV) -> ResultadoPDV: ...


class RegistroReconciliacao(Protocol):
    def registrar_falha_shadow(
        self, entrada: EntradaPDV, venda_legada_id: str | None, motivo: str
    ) -> None: ...


class UnitOfWorkPDV(AbstractContextManager["UnitOfWorkPDV"], Protocol):
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
