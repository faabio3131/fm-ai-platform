"""Ledger canônico de cashback do CRM.

Movimentos são append-only. A projeção de saldo existe apenas para leitura rápida e
controle transacional de concorrência; a trilha de movimentos permanece a fonte de
verdade auditável.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from .erros import ErroCRM
from .modelos import moeda


class TipoMovimentoCashback(StrEnum):
    CREDITO = "credito"
    DEBITO = "debito"


@dataclass(frozen=True)
class MovimentoCashback:
    movimento_id: str
    tenant_id: str
    unidade_id: str
    cliente_id: str
    tipo: TipoMovimentoCashback
    valor: Decimal
    origem: str
    referencia: str
    ocorrido_em: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        campos = (
            self.movimento_id,
            self.tenant_id,
            self.unidade_id,
            self.cliente_id,
            self.origem,
            self.referencia,
            self.idempotency_key,
        )
        if any(not valor.strip() for valor in campos):
            raise ErroCRM("movimento_cashback_invalido")
        valor = moeda(self.valor)
        if valor <= 0:
            raise ErroCRM("movimento_cashback_valor_invalido")
        instante = self.ocorrido_em
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ErroCRM("timestamp_sem_timezone")
        object.__setattr__(self, "valor", valor)
        object.__setattr__(self, "ocorrido_em", instante.astimezone(timezone.utc))

    @property
    def valor_assinado(self) -> Decimal:
        return self.valor if self.tipo is TipoMovimentoCashback.CREDITO else -self.valor


@dataclass(frozen=True)
class ResultadoMovimentoCashback:
    movimento: MovimentoCashback
    saldo: Decimal
    idempotente: bool = False


class PortaLedgerCashback(Protocol):
    def aplicar(
        self, movimento: MovimentoCashback
    ) -> tuple[MovimentoCashback, bool]: ...

    def saldo(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> Decimal: ...

    def historico(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> tuple[MovimentoCashback, ...]: ...


def _movimento_id(idempotency_key: str) -> str:
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24]
    return f"cbmov_{digest}"


class ServicoCashback:
    """Constrói movimentos válidos e delega a aplicação atômica ao ledger."""

    def __init__(self, ledger: PortaLedgerCashback) -> None:
        self.ledger = ledger

    @staticmethod
    def _instante(valor: datetime | None) -> datetime:
        instante = valor or datetime.now(timezone.utc)
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ErroCRM("timestamp_sem_timezone")
        return instante.astimezone(timezone.utc)

    def _aplicar(
        self,
        *,
        tipo: TipoMovimentoCashback,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        valor: Decimal,
        origem: str,
        referencia: str,
        idempotency_key: str,
        ocorrido_em: datetime | None,
    ) -> ResultadoMovimentoCashback:
        if not idempotency_key.strip():
            raise ErroCRM("idempotencia_cashback_obrigatoria")
        movimento = MovimentoCashback(
            movimento_id=_movimento_id(idempotency_key),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            tipo=tipo,
            valor=valor,
            origem=origem,
            referencia=referencia,
            ocorrido_em=self._instante(ocorrido_em),
            idempotency_key=idempotency_key,
        )
        salvo, idempotente = self.ledger.aplicar(movimento)
        saldo = self.ledger.saldo(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
        )
        return ResultadoMovimentoCashback(salvo, saldo, idempotente)

    def creditar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        valor: Decimal,
        origem: str,
        referencia: str,
        idempotency_key: str,
        ocorrido_em: datetime | None = None,
    ) -> ResultadoMovimentoCashback:
        return self._aplicar(
            tipo=TipoMovimentoCashback.CREDITO,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            valor=valor,
            origem=origem,
            referencia=referencia,
            idempotency_key=idempotency_key,
            ocorrido_em=ocorrido_em,
        )

    def debitar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_id: str,
        valor: Decimal,
        origem: str,
        referencia: str,
        idempotency_key: str,
        ocorrido_em: datetime | None = None,
    ) -> ResultadoMovimentoCashback:
        return self._aplicar(
            tipo=TipoMovimentoCashback.DEBITO,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=cliente_id,
            valor=valor,
            origem=origem,
            referencia=referencia,
            idempotency_key=idempotency_key,
            ocorrido_em=ocorrido_em,
        )
