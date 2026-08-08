"""Ledger SQL append-only, escopado, com saldo materializado por CAS."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .erros import ConflitoIdempotenciaEstoque, ConcorrenciaEstoque, SaldoInsuficiente
from .modelos import MovimentoEstoque, SaldoEstoque, TipoMovimento
from .modelos_orm import MovimentoEstoqueORM, SaldoEstoqueORM
from .repositorios import _aplicar


class RepositorioLedgerSQLAlchemy:
    """Nao oferece update/delete de ledger por desenho."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def consultar_saldo(
        self, tenant_id: str, unidade_id: str, insumo_id: str
    ) -> SaldoEstoque:
        row = self._session.get(SaldoEstoqueORM, (tenant_id, unidade_id, insumo_id))
        if row is None:
            return SaldoEstoque(
                tenant_id, unidade_id, insumo_id, Decimal(0), Decimal(0), 0
            )
        return SaldoEstoque(
            tenant_id,
            unidade_id,
            insumo_id,
            Decimal(str(row.saldo_fisico)),
            Decimal(str(row.saldo_reservado)),
            row.versao,
        )

    def append(
        self,
        movimento: MovimentoEstoque,
        *,
        versao_esperada: int | None = None,
        permitir_negativo: bool = False,
    ) -> MovimentoEstoque:
        saldo = self.consultar_saldo(
            movimento.tenant_id, movimento.unidade_id, movimento.insumo_id
        )
        esperado = saldo.versao if versao_esperada is None else versao_esperada
        if esperado != saldo.versao:
            raise ConcorrenciaEstoque("versao_estoque_divergente")
        fisico, reservado = _aplicar(saldo, movimento)
        if (fisico < 0 or fisico - reservado < 0) and not permitir_negativo:
            raise SaldoInsuficiente("saldo_disponivel_insuficiente")
        if saldo.versao == 0:
            stmt: Any = insert(SaldoEstoqueORM).values(
                tenant_id=movimento.tenant_id,
                unidade_id=movimento.unidade_id,
                insumo_id=movimento.insumo_id,
                saldo_fisico=fisico,
                saldo_reservado=reservado,
                versao=1,
            )
        else:
            stmt = (
                update(SaldoEstoqueORM)
                .where(
                    SaldoEstoqueORM.tenant_id == movimento.tenant_id,
                    SaldoEstoqueORM.unidade_id == movimento.unidade_id,
                    SaldoEstoqueORM.insumo_id == movimento.insumo_id,
                    SaldoEstoqueORM.versao == esperado,
                )
                .values(
                    saldo_fisico=fisico, saldo_reservado=reservado, versao=esperado + 1
                )
            )
        try:
            resultado = self._session.execute(stmt)
            if saldo.versao and getattr(resultado, "rowcount", 0) != 1:
                raise ConcorrenciaEstoque("compare_and_swap_falhou")
            self._session.add(
                MovimentoEstoqueORM(
                    movimento_id=movimento.movimento_id,
                    tenant_id=movimento.tenant_id,
                    unidade_id=movimento.unidade_id,
                    insumo_id=movimento.insumo_id,
                    tipo_movimento=movimento.tipo_movimento.value,
                    quantidade=movimento.quantidade,
                    unidade_medida=movimento.unidade_medida,
                    origem_tipo=movimento.origem_tipo,
                    origem_id=movimento.origem_id,
                    origem_versao=movimento.origem_versao,
                    idempotency_key=movimento.idempotency_key,
                    occurred_at=movimento.occurred_at,
                    correlation_id=movimento.correlation_id,
                    causation_id=movimento.causation_id,
                    ator=movimento.ator,
                    motivo=movimento.motivo,
                    metadata_segura=dict(movimento.metadata),
                )
            )
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoIdempotenciaEstoque("movimento_duplicado") from exc
        return movimento

    def listar_movimentos(
        self, tenant_id: str, unidade_id: str, insumo_id: str | None = None
    ) -> tuple[MovimentoEstoque, ...]:
        stmt = select(MovimentoEstoqueORM).where(
            MovimentoEstoqueORM.tenant_id == tenant_id,
            MovimentoEstoqueORM.unidade_id == unidade_id,
        )
        if insumo_id is not None:
            stmt = stmt.where(MovimentoEstoqueORM.insumo_id == insumo_id)
        rows = self._session.scalars(
            stmt.order_by(
                MovimentoEstoqueORM.occurred_at, MovimentoEstoqueORM.movimento_id
            )
        ).all()
        return tuple(
            MovimentoEstoque(
                r.movimento_id,
                r.tenant_id,
                r.unidade_id,
                r.insumo_id,
                TipoMovimento(r.tipo_movimento),
                Decimal(str(r.quantidade)),
                r.unidade_medida,
                r.origem_tipo,
                r.origem_id,
                r.origem_versao,
                r.idempotency_key,
                (
                    cast(datetime, r.occurred_at).replace(tzinfo=timezone.utc)
                    if cast(datetime, r.occurred_at).tzinfo is None
                    else cast(datetime, r.occurred_at)
                ),
                r.correlation_id,
                r.causation_id,
                r.ator,
                r.motivo,
                r.metadata_segura,
            )
            for r in rows
        )
