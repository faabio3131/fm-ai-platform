"""Persistência transacional do ledger canônico de cashback."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from core.crm.cashback import MovimentoCashback, TipoMovimentoCashback
from core.crm.erros import ErroCRM
from core.crm.modelos import moeda
from infra.crm.cashback_schema import (
    crm_cashback_movimentos_v1,
    crm_cashback_saldos_v1,
)


class RepositorioCashbackSQLAlchemy:
    """Ledger append-only + projeção de saldo bloqueável na mesma transação."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _instante(valor: object) -> datetime:
        if not isinstance(valor, datetime):
            raise TypeError("cashback_ocorrido_em_invalido")
        if valor.tzinfo is None or valor.utcoffset() is None:
            return valor.replace(tzinfo=timezone.utc)
        return valor.astimezone(timezone.utc)

    @staticmethod
    def _mesma_semantica(
        existente: MovimentoCashback, novo: MovimentoCashback
    ) -> bool:
        return (
            existente.tenant_id,
            existente.unidade_id,
            existente.cliente_id,
            existente.tipo,
            existente.valor,
            existente.origem,
            existente.referencia,
        ) == (
            novo.tenant_id,
            novo.unidade_id,
            novo.cliente_id,
            novo.tipo,
            novo.valor,
            novo.origem,
            novo.referencia,
        )

    def _mapear(self, row) -> MovimentoCashback:
        return MovimentoCashback(
            movimento_id=str(row["movimento_id"]),
            tenant_id=str(row["tenant_id"]),
            unidade_id=str(row["unidade_id"]),
            cliente_id=str(row["cliente_id"]),
            tipo=TipoMovimentoCashback(str(row["tipo"])),
            valor=Decimal(str(row["valor"])),
            origem=str(row["origem"]),
            referencia=str(row["referencia"]),
            ocorrido_em=self._instante(row["ocorrido_em"]),
            idempotency_key=str(row["idempotency_key"]),
        )

    def _por_idempotencia(
        self, *, tenant_id: str, unidade_id: str, idempotency_key: str
    ) -> MovimentoCashback | None:
        row = self._session.execute(
            select(crm_cashback_movimentos_v1).where(
                crm_cashback_movimentos_v1.c.tenant_id == tenant_id,
                crm_cashback_movimentos_v1.c.unidade_id == unidade_id,
                crm_cashback_movimentos_v1.c.idempotency_key == idempotency_key,
            )
        ).mappings().one_or_none()
        return None if row is None else self._mapear(row)

    def _saldo_bloqueado(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ):
        return self._session.execute(
            select(crm_cashback_saldos_v1)
            .where(
                crm_cashback_saldos_v1.c.tenant_id == tenant_id,
                crm_cashback_saldos_v1.c.unidade_id == unidade_id,
                crm_cashback_saldos_v1.c.cliente_id == cliente_id,
            )
            .with_for_update()
        ).mappings().one_or_none()

    def aplicar(
        self, movimento: MovimentoCashback
    ) -> tuple[MovimentoCashback, bool]:
        existente = self._por_idempotencia(
            tenant_id=movimento.tenant_id,
            unidade_id=movimento.unidade_id,
            idempotency_key=movimento.idempotency_key,
        )
        if existente is not None:
            if not self._mesma_semantica(existente, movimento):
                raise ErroCRM("conflito_idempotencia_cashback")
            return existente, True

        saldo_row = self._saldo_bloqueado(
            tenant_id=movimento.tenant_id,
            unidade_id=movimento.unidade_id,
            cliente_id=movimento.cliente_id,
        )
        saldo_atual = (
            Decimal("0.00")
            if saldo_row is None
            else moeda(Decimal(str(saldo_row["saldo"])))
        )
        versao = 0 if saldo_row is None else int(saldo_row["versao"])

        if movimento.tipo is TipoMovimentoCashback.DEBITO:
            if saldo_row is None or saldo_atual < movimento.valor:
                raise ErroCRM("cashback_saldo_insuficiente")
            novo_saldo = moeda(saldo_atual - movimento.valor)
        else:
            novo_saldo = moeda(saldo_atual + movimento.valor)

        self._session.execute(
            insert(crm_cashback_movimentos_v1).values(
                tenant_id=movimento.tenant_id,
                unidade_id=movimento.unidade_id,
                movimento_id=movimento.movimento_id,
                cliente_id=movimento.cliente_id,
                tipo=movimento.tipo.value,
                valor=movimento.valor,
                origem=movimento.origem,
                referencia=movimento.referencia,
                ocorrido_em=movimento.ocorrido_em,
                idempotency_key=movimento.idempotency_key,
            )
        )

        if saldo_row is None:
            self._session.execute(
                insert(crm_cashback_saldos_v1).values(
                    tenant_id=movimento.tenant_id,
                    unidade_id=movimento.unidade_id,
                    cliente_id=movimento.cliente_id,
                    saldo=novo_saldo,
                    versao=1,
                )
            )
        else:
            resultado = self._session.execute(
                update(crm_cashback_saldos_v1)
                .where(
                    crm_cashback_saldos_v1.c.tenant_id == movimento.tenant_id,
                    crm_cashback_saldos_v1.c.unidade_id == movimento.unidade_id,
                    crm_cashback_saldos_v1.c.cliente_id == movimento.cliente_id,
                    crm_cashback_saldos_v1.c.versao == versao,
                )
                .values(saldo=novo_saldo, versao=versao + 1)
            )
            if resultado.rowcount != 1:
                raise ErroCRM("conflito_concorrencia_cashback")

        self._session.flush()
        return movimento, False

    def saldo(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> Decimal:
        valor = self._session.scalar(
            select(crm_cashback_saldos_v1.c.saldo).where(
                crm_cashback_saldos_v1.c.tenant_id == tenant_id,
                crm_cashback_saldos_v1.c.unidade_id == unidade_id,
                crm_cashback_saldos_v1.c.cliente_id == cliente_id,
            )
        )
        return Decimal("0.00") if valor is None else moeda(Decimal(str(valor)))

    def historico(
        self, *, tenant_id: str, unidade_id: str, cliente_id: str
    ) -> tuple[MovimentoCashback, ...]:
        rows = self._session.execute(
            select(crm_cashback_movimentos_v1)
            .where(
                crm_cashback_movimentos_v1.c.tenant_id == tenant_id,
                crm_cashback_movimentos_v1.c.unidade_id == unidade_id,
                crm_cashback_movimentos_v1.c.cliente_id == cliente_id,
            )
            .order_by(
                crm_cashback_movimentos_v1.c.ocorrido_em,
                crm_cashback_movimentos_v1.c.movimento_id,
            )
        ).mappings().all()
        return tuple(self._mapear(row) for row in rows)
