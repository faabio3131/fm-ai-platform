"""Portas transacionais: core nao conhece modelos SQLAlchemy legados do app."""

from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from .modelos import EntradaPDV, ResultadoPDV


class ExecutorLegado(Protocol):
    def executar(self, entrada: EntradaPDV) -> ResultadoPDV: ...


class PonteCatalogoLegadoPDV(Protocol):
    """Leitura legada mínima para ancorar o cutover canônico."""

    def validar_estoque(self, entrada: EntradaPDV) -> list[tuple[Any, Decimal]]: ...


class ProjecaoCompatLegadaPDV(Protocol):
    """Projeções compatíveis sem autoridade financeira ou de estoque."""

    def criar_venda_uma_vez(
        self,
        entrada: EntradaPDV,
        *,
        instante: datetime,
        status: str = "Aprovado",
    ) -> Any: ...

    def aplicar_cashback_uma_vez(
        self,
        entrada: EntradaPDV,
        instante: datetime,
    ) -> None: ...


class PonteProjecaoCompatLegadaPDV(
    PonteCatalogoLegadoPDV,
    ProjecaoCompatLegadaPDV,
    Protocol,
):
    """Capability set mínimo permitido ao executor canônico."""


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
