"""Repository SQLAlchemy escopado da Expedição e Entrega V1."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .erros import ErroEntrega
from .modelos import Entrega, ModalidadeEntrega, StatusEntrega
from .modelos_orm import EntregaORM, EventoEntregaORM


def _utc(valor: object | None) -> datetime | None:
    if valor is None:
        return None
    instante = cast(datetime, valor)
    if instante.tzinfo is None:
        return instante.replace(tzinfo=timezone.utc)
    return instante.astimezone(timezone.utc)


class RepositorioEntregaSQLAlchemy:
    """Persistência sem commit implícito; transação pertence ao chamador."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def buscar(self, tenant_id: str, unidade_id: str, entrega_id: str) -> Entrega | None:
        row = self.session.scalar(
            select(EntregaORM).where(
                EntregaORM.tenant_id == tenant_id,
                EntregaORM.unidade_id == unidade_id,
                EntregaORM.id == entrega_id,
            )
        )
        return self._dominio(row) if row else None

    def buscar_por_pedido(
        self, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> Entrega | None:
        row = self.session.scalar(
            select(EntregaORM).where(
                EntregaORM.tenant_id == tenant_id,
                EntregaORM.unidade_id == unidade_id,
                EntregaORM.pedido_id == pedido_id,
            )
        )
        return self._dominio(row) if row else None

    def listar(self, tenant_id: str, unidade_id: str) -> tuple[Entrega, ...]:
        rows = self.session.scalars(
            select(EntregaORM)
            .where(
                EntregaORM.tenant_id == tenant_id,
                EntregaORM.unidade_id == unidade_id,
            )
            .order_by(EntregaORM.status, EntregaORM.atualizado_em, EntregaORM.id)
        ).all()
        return tuple(self._dominio(row) for row in rows)

    def salvar_nova(self, entrega: Entrega, *, atualizado_em: datetime) -> Entrega:
        if entrega.versao != 1 or entrega.status is not StatusEntrega.AGUARDANDO_PRODUCAO:
            raise ErroEntrega("entrega_nova_invalida")
        if self.buscar_por_pedido(entrega.tenant_id, entrega.unidade_id, entrega.pedido_id):
            raise ErroEntrega("entrega_pedido_ja_existe")
        self.session.add(
            EntregaORM(
                id=entrega.entrega_id,
                tenant_id=entrega.tenant_id,
                unidade_id=entrega.unidade_id,
                pedido_id=entrega.pedido_id,
                endereco_id=entrega.endereco_id,
                modalidade=entrega.modalidade.value,
                status=entrega.status.value,
                versao=entrega.versao,
                tentativa=entrega.tentativa,
                entregador_id=entrega.entregador_id,
                producao_pronta_em=entrega.producao_pronta_em,
                checklist_concluido_em=entrega.checklist_concluido_em,
                atribuida_em=entrega.atribuida_em,
                coletada_em=entrega.coletada_em,
                saiu_em=entrega.saiu_em,
                entregue_em=entrega.entregue_em,
                prova_entrega_ref=entrega.prova_entrega_ref,
                atualizado_em=atualizado_em,
            )
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ErroEntrega("conflito_persistencia_entrega") from exc
        return entrega

    def salvar(
        self,
        entrega: Entrega,
        *,
        versao_esperada: int,
        atualizado_em: datetime,
    ) -> Entrega:
        resultado = cast(
            CursorResult[Any],
            self.session.execute(
                update(EntregaORM)
                .where(
                    EntregaORM.tenant_id == entrega.tenant_id,
                    EntregaORM.unidade_id == entrega.unidade_id,
                    EntregaORM.id == entrega.entrega_id,
                    EntregaORM.versao == versao_esperada,
                )
                .values(
                    status=entrega.status.value,
                    versao=entrega.versao,
                    tentativa=entrega.tentativa,
                    entregador_id=entrega.entregador_id,
                    producao_pronta_em=entrega.producao_pronta_em,
                    checklist_concluido_em=entrega.checklist_concluido_em,
                    atribuida_em=entrega.atribuida_em,
                    coletada_em=entrega.coletada_em,
                    saiu_em=entrega.saiu_em,
                    entregue_em=entrega.entregue_em,
                    prova_entrega_ref=entrega.prova_entrega_ref,
                    atualizado_em=atualizado_em,
                )
            ),
        )
        if resultado.rowcount != 1:
            raise ErroEntrega("compare_and_swap_falhou")
        self.session.flush()
        return entrega

    def buscar_evento_idempotente(
        self, tenant_id: str, unidade_id: str, idempotency_key: str
    ) -> EventoEntregaORM | None:
        return self.session.scalar(
            select(EventoEntregaORM).where(
                EventoEntregaORM.tenant_id == tenant_id,
                EventoEntregaORM.unidade_id == unidade_id,
                EventoEntregaORM.idempotency_key == idempotency_key,
            )
        )

    def append_evento(
        self,
        *,
        event_id: str,
        entrega: Entrega,
        tipo: str,
        ator_id: str,
        correlation_id: str,
        causation_id: str | None,
        idempotency_key: str,
        request_hash: str,
        ocorrido_em: datetime,
        payload_seguro: dict[str, object],
    ) -> None:
        self.session.add(
            EventoEntregaORM(
                event_id=event_id,
                tenant_id=entrega.tenant_id,
                unidade_id=entrega.unidade_id,
                entrega_id=entrega.entrega_id,
                pedido_id=entrega.pedido_id,
                tipo=tipo,
                ator_id=ator_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                ocorrido_em=ocorrido_em,
                versao_entrega=entrega.versao,
                payload_seguro=payload_seguro,
            )
        )
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise ErroEntrega("conflito_idempotencia") from exc

    def listar_eventos(
        self, tenant_id: str, unidade_id: str, entrega_id: str
    ) -> tuple[EventoEntregaORM, ...]:
        return tuple(
            self.session.scalars(
                select(EventoEntregaORM)
                .where(
                    EventoEntregaORM.tenant_id == tenant_id,
                    EventoEntregaORM.unidade_id == unidade_id,
                    EventoEntregaORM.entrega_id == entrega_id,
                )
                .order_by(EventoEntregaORM.ocorrido_em, EventoEntregaORM.event_id)
            ).all()
        )

    @staticmethod
    def _dominio(row: EntregaORM) -> Entrega:
        return Entrega(
            entrega_id=row.id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            pedido_id=row.pedido_id,
            endereco_id=row.endereco_id,
            modalidade=ModalidadeEntrega(row.modalidade),
            status=StatusEntrega(row.status),
            versao=row.versao,
            tentativa=row.tentativa,
            entregador_id=row.entregador_id,
            producao_pronta_em=_utc(row.producao_pronta_em),
            checklist_concluido_em=_utc(row.checklist_concluido_em),
            atribuida_em=_utc(row.atribuida_em),
            coletada_em=_utc(row.coletada_em),
            saiu_em=_utc(row.saiu_em),
            entregue_em=_utc(row.entregue_em),
            prova_entrega_ref=row.prova_entrega_ref,
        )
