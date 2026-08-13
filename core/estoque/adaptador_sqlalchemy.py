"""Ledger SQL append-only, escopado, com saldo materializado por CAS."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TypeVar, cast

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .erros import ConcorrenciaEstoque, ConflitoIdempotenciaEstoque, SaldoInsuficiente
from .modelos import (
    ItemSnapshotFicha,
    MovimentoEstoque,
    ReservaEstoque,
    SaldoEstoque,
    SnapshotFichaEstoque,
    StatusReserva,
    TipoMovimento,
)
from .modelos_orm import MovimentoEstoqueORM, ReservaEstoqueORM, SaldoEstoqueORM
from .repositorios import _aplicar

T = TypeVar("T")


def _utc(value: object) -> datetime:
    instant = cast(datetime, value)
    return (
        instant.replace(tzinfo=timezone.utc)
        if instant.tzinfo is None
        else instant.astimezone(timezone.utc)
    )


def _movimento_from_row(row: MovimentoEstoqueORM) -> MovimentoEstoque:
    return MovimentoEstoque(
        row.movimento_id,
        row.tenant_id,
        row.unidade_id,
        row.insumo_id,
        TipoMovimento(row.tipo_movimento),
        Decimal(str(row.quantidade)),
        row.unidade_medida,
        row.origem_tipo,
        row.origem_id,
        row.origem_versao,
        row.idempotency_key,
        _utc(row.occurred_at),
        row.correlation_id,
        row.causation_id,
        row.ator,
        row.motivo,
        row.metadata_segura,
    )


def _snapshot_to_dict(snapshot: SnapshotFichaEstoque) -> dict[str, Any]:
    return {
        "pedido_id": snapshot.pedido_id,
        "versao_ficha": snapshot.versao_ficha,
        "capturado_em": snapshot.capturado_em.isoformat(),
        "itens": [
            {
                "produto_id": item.produto_id,
                "item_pedido_id": item.item_pedido_id,
                "insumo_id": item.insumo_id,
                "quantidade_por_unidade": str(item.quantidade_por_unidade),
                "quantidade_total": str(item.quantidade_total),
                "unidade_medida": item.unidade_medida,
            }
            for item in snapshot.itens
        ],
    }


def _snapshot_from_dict(payload: dict[str, Any]) -> SnapshotFichaEstoque:
    itens_raw = payload.get("itens")
    if not isinstance(itens_raw, list):
        raise TypeError("snapshot de estoque persistido invalido")
    return SnapshotFichaEstoque(
        pedido_id=str(payload["pedido_id"]),
        versao_ficha=str(payload["versao_ficha"]),
        capturado_em=datetime.fromisoformat(str(payload["capturado_em"])),
        itens=tuple(
            ItemSnapshotFicha(
                produto_id=str(item["produto_id"]),
                item_pedido_id=str(item["item_pedido_id"]),
                insumo_id=str(item["insumo_id"]),
                quantidade_por_unidade=Decimal(str(item["quantidade_por_unidade"])),
                quantidade_total=Decimal(str(item["quantidade_total"])),
                unidade_medida=str(item["unidade_medida"]),
            )
            for item in itens_raw
            if isinstance(item, dict)
        ),
    )


def _snapshot_hash(snapshot: SnapshotFichaEstoque) -> str:
    payload = _snapshot_to_dict(snapshot)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reserva_from_row(row: ReservaEstoqueORM) -> ReservaEstoque:
    return ReservaEstoque(
        reserva_id=row.reserva_id,
        tenant_id=row.tenant_id,
        unidade_id=row.unidade_id,
        pedido_id=row.pedido_id,
        pedido_versao=row.pedido_versao,
        snapshot=_snapshot_from_dict(dict(row.snapshot)),
        status=StatusReserva(row.status),
        idempotency_key=row.idempotency_key,
        criada_em=_utc(row.criada_em),
        resolvida_em=_utc(row.resolvida_em) if row.resolvida_em is not None else None,
    )


class RepositorioLedgerSQLAlchemy:
    """Implementa a porta de estoque sem update/delete do ledger."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def executar_atomicamente(self, operacao: Callable[[], T]) -> T:
        """A fronteira de commit/rollback pertence ao Unit of Work chamador."""

        return operacao()

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
        por_chave = self.por_idempotencia(
            movimento.tenant_id, movimento.unidade_id, movimento.idempotency_key
        )
        if por_chave:
            if len(por_chave) == 1 and por_chave[0] == movimento:
                return por_chave[0]
            raise ConflitoIdempotenciaEstoque("conflito_idempotencia")

        logico = self._session.scalar(
            select(MovimentoEstoqueORM).where(
                MovimentoEstoqueORM.tenant_id == movimento.tenant_id,
                MovimentoEstoqueORM.unidade_id == movimento.unidade_id,
                MovimentoEstoqueORM.origem_tipo == movimento.origem_tipo,
                MovimentoEstoqueORM.origem_id == movimento.origem_id,
                MovimentoEstoqueORM.tipo_movimento == movimento.tipo_movimento.value,
                MovimentoEstoqueORM.insumo_id == movimento.insumo_id,
                MovimentoEstoqueORM.origem_versao == movimento.origem_versao,
            )
        )
        if logico is not None:
            raise ConflitoIdempotenciaEstoque("movimento_logico_duplicado")

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
        return tuple(_movimento_from_row(row) for row in rows)

    def por_idempotencia(
        self, tenant_id: str, unidade_id: str, chave: str
    ) -> tuple[MovimentoEstoque, ...]:
        rows = self._session.scalars(
            select(MovimentoEstoqueORM)
            .where(
                MovimentoEstoqueORM.tenant_id == tenant_id,
                MovimentoEstoqueORM.unidade_id == unidade_id,
                MovimentoEstoqueORM.idempotency_key == chave,
            )
            .order_by(MovimentoEstoqueORM.occurred_at, MovimentoEstoqueORM.movimento_id)
        ).all()
        return tuple(_movimento_from_row(row) for row in rows)

    def por_origem(
        self, tenant_id: str, unidade_id: str, origem_tipo: str, origem_id: str
    ) -> tuple[MovimentoEstoque, ...]:
        rows = self._session.scalars(
            select(MovimentoEstoqueORM)
            .where(
                MovimentoEstoqueORM.tenant_id == tenant_id,
                MovimentoEstoqueORM.unidade_id == unidade_id,
                MovimentoEstoqueORM.origem_tipo == origem_tipo,
                MovimentoEstoqueORM.origem_id == origem_id,
            )
            .order_by(MovimentoEstoqueORM.occurred_at, MovimentoEstoqueORM.movimento_id)
        ).all()
        return tuple(_movimento_from_row(row) for row in rows)

    def salvar_reserva(self, reserva: ReservaEstoque) -> None:
        atual = self._session.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.tenant_id == reserva.tenant_id,
                ReservaEstoqueORM.unidade_id == reserva.unidade_id,
                ReservaEstoqueORM.pedido_id == reserva.pedido_id,
            )
        )
        snapshot_payload = _snapshot_to_dict(reserva.snapshot)
        snapshot_hash = _snapshot_hash(reserva.snapshot)
        if atual is None:
            self._session.add(
                ReservaEstoqueORM(
                    reserva_id=reserva.reserva_id,
                    tenant_id=reserva.tenant_id,
                    unidade_id=reserva.unidade_id,
                    pedido_id=reserva.pedido_id,
                    pedido_versao=reserva.pedido_versao,
                    snapshot=snapshot_payload,
                    snapshot_hash=snapshot_hash,
                    status=reserva.status.value,
                    idempotency_key=reserva.idempotency_key,
                    criada_em=reserva.criada_em,
                    resolvida_em=reserva.resolvida_em,
                )
            )
        else:
            if atual.idempotency_key != reserva.idempotency_key:
                raise ConflitoIdempotenciaEstoque("reserva_existente")
            if atual.snapshot_hash != snapshot_hash:
                raise ConflitoIdempotenciaEstoque("conflito_snapshot_reserva")
            atual.pedido_versao = reserva.pedido_versao
            atual.status = reserva.status.value
            atual.resolvida_em = reserva.resolvida_em
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoIdempotenciaEstoque("reserva_duplicada") from exc

    def buscar_reserva(
        self, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> ReservaEstoque | None:
        row = self._session.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.tenant_id == tenant_id,
                ReservaEstoqueORM.unidade_id == unidade_id,
                ReservaEstoqueORM.pedido_id == pedido_id,
            )
        )
        return _reserva_from_row(row) if row else None
