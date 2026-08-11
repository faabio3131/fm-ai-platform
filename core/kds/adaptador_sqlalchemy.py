"""Persistencia SQLAlchemy do KDS V1, sempre escopada por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import and_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from core.pedidos.modelos_orm import ItemPedidoORM

from .erros import ErroKDS
from .modelos import ProducaoItem, SetorProducao
from .modelos_orm import EventoProducaoORM, ProducaoItemORM, SetorProducaoORM


def _utc(valor: Any) -> datetime:
    instante = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    return (
        instante.replace(tzinfo=timezone.utc)
        if instante.tzinfo is None
        else instante.astimezone(timezone.utc)
    )


def _setor(orm: SetorProducaoORM) -> SetorProducao:
    return SetorProducao(
        setor_id=orm.id,
        tenant_id=orm.tenant_id,
        unidade_id=orm.unidade_id,
        codigo=orm.codigo,
        nome=orm.nome,
        ordem=orm.ordem,
        sla_segundos=orm.sla_segundos,
        ativo=orm.ativo,
        criado_em=_utc(orm.criado_em),
        atualizado_em=_utc(orm.atualizado_em),
    )


def _producao(orm: ProducaoItemORM) -> ProducaoItem:
    opcionais = {
        campo: (_utc(getattr(orm, campo)) if getattr(orm, campo) is not None else None)
        for campo in (
            "aceita_em",
            "iniciada_em",
            "pausa_iniciada_em",
            "pronta_em",
            "retirada_em",
        )
    }
    return ProducaoItem(
        producao_id=orm.id,
        tenant_id=orm.tenant_id,
        unidade_id=orm.unidade_id,
        pedido_id=orm.pedido_id,
        pedido_item_id=orm.pedido_item_id,
        setor_id=orm.setor_id,
        status=orm.status,
        prioridade=orm.prioridade,
        quantidade=Decimal(str(orm.quantidade)),
        tentativa=orm.tentativa,
        versao=orm.versao,
        criado_em=_utc(orm.criado_em),
        atualizado_em=_utc(orm.atualizado_em),
        aceita_em=opcionais["aceita_em"],
        iniciada_em=opcionais["iniciada_em"],
        pausa_iniciada_em=opcionais["pausa_iniciada_em"],
        pronta_em=opcionais["pronta_em"],
        retirada_em=opcionais["retirada_em"],
        responsavel_id=orm.responsavel_id,
        pausa_acumulada_segundos=orm.pausa_acumulada_segundos,
    )


class RepositorioKDSSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar_setores(
        self, tenant_id: str, unidade_id: str, *, somente_ativos: bool = True
    ) -> tuple[SetorProducao, ...]:
        stmt = select(SetorProducaoORM).where(
            SetorProducaoORM.tenant_id == tenant_id,
            SetorProducaoORM.unidade_id == unidade_id,
        )
        if somente_ativos:
            stmt = stmt.where(SetorProducaoORM.ativo.is_(True))
        stmt = stmt.order_by(SetorProducaoORM.ordem, SetorProducaoORM.codigo)
        return tuple(_setor(item) for item in self.session.scalars(stmt))

    def obter_setor(
        self, tenant_id: str, unidade_id: str, setor_id: str
    ) -> SetorProducao | None:
        orm = self.session.get(SetorProducaoORM, (setor_id, tenant_id, unidade_id))
        return _setor(orm) if orm else None

    def criar_setor(self, setor: SetorProducao) -> SetorProducao:
        existente = self.session.scalar(
            select(SetorProducaoORM).where(
                SetorProducaoORM.tenant_id == setor.tenant_id,
                SetorProducaoORM.unidade_id == setor.unidade_id,
                SetorProducaoORM.codigo == setor.codigo,
            )
        )
        if existente:
            atual = _setor(existente)
            if (
                atual.nome,
                atual.ordem,
                atual.sla_segundos,
                atual.ativo,
            ) != (setor.nome, setor.ordem, setor.sla_segundos, setor.ativo):
                raise ErroKDS("setor_codigo_conflitante")
            return atual
        self.session.add(
            SetorProducaoORM(
                id=setor.setor_id,
                tenant_id=setor.tenant_id,
                unidade_id=setor.unidade_id,
                codigo=setor.codigo,
                nome=setor.nome,
                ordem=setor.ordem,
                sla_segundos=setor.sla_segundos,
                ativo=setor.ativo,
                criado_em=setor.criado_em,
                atualizado_em=setor.atualizado_em,
            )
        )
        self.session.flush()
        return setor

    def obter_producao(
        self, tenant_id: str, unidade_id: str, producao_id: str
    ) -> ProducaoItem | None:
        orm = self.session.get(ProducaoItemORM, (producao_id, tenant_id, unidade_id))
        return _producao(orm) if orm else None

    def rotear(
        self,
        producao: ProducaoItem,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> ProducaoItem:
        repetida = self.session.scalar(
            select(ProducaoItemORM).where(
                ProducaoItemORM.tenant_id == producao.tenant_id,
                ProducaoItemORM.unidade_id == producao.unidade_id,
                ProducaoItemORM.idempotency_key == idempotency_key,
            )
        )
        if repetida:
            if repetida.request_hash != request_hash:
                raise ErroKDS("conflito_idempotencia")
            return _producao(repetida)

        setor = self.session.get(
            SetorProducaoORM,
            (producao.setor_id, producao.tenant_id, producao.unidade_id),
        )
        if setor is None or not setor.ativo:
            raise ErroKDS("setor_indisponivel")

        item = self.session.scalar(
            select(ItemPedidoORM).where(
                ItemPedidoORM.tenant_id == producao.tenant_id,
                ItemPedidoORM.unidade_id == producao.unidade_id,
                ItemPedidoORM.id == producao.pedido_item_id,
                ItemPedidoORM.pedido_id == producao.pedido_id,
            )
        )
        if item is None:
            raise ErroKDS("pedido_item_inexistente")

        self.session.add(
            ProducaoItemORM(
                id=producao.producao_id,
                tenant_id=producao.tenant_id,
                unidade_id=producao.unidade_id,
                pedido_id=producao.pedido_id,
                pedido_item_id=producao.pedido_item_id,
                setor_id=producao.setor_id,
                status=producao.status,
                prioridade=producao.prioridade,
                quantidade=producao.quantidade,
                tentativa=producao.tentativa,
                versao=producao.versao,
                criado_em=producao.criado_em,
                atualizado_em=producao.atualizado_em,
                aceita_em=producao.aceita_em,
                iniciada_em=producao.iniciada_em,
                pausa_iniciada_em=producao.pausa_iniciada_em,
                pronta_em=producao.pronta_em,
                retirada_em=producao.retirada_em,
                responsavel_id=producao.responsavel_id,
                pausa_acumulada_segundos=producao.pausa_acumulada_segundos,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
            )
        )
        self.session.flush()
        return producao

    def listar_fila(
        self,
        tenant_id: str,
        unidade_id: str,
        *,
        setor_id: str | None = None,
        statuses: tuple[str, ...] = (
            "aguardando",
            "aceita",
            "em_preparo",
            "pausada",
            "pronta",
        ),
    ) -> tuple[tuple[ProducaoItem, SetorProducao], ...]:
        condicao_setor = and_(
            SetorProducaoORM.id == ProducaoItemORM.setor_id,
            SetorProducaoORM.tenant_id == ProducaoItemORM.tenant_id,
            SetorProducaoORM.unidade_id == ProducaoItemORM.unidade_id,
        )
        stmt = (
            select(ProducaoItemORM, SetorProducaoORM)
            .join(SetorProducaoORM, condicao_setor)
            .where(
                ProducaoItemORM.tenant_id == tenant_id,
                ProducaoItemORM.unidade_id == unidade_id,
                ProducaoItemORM.status.in_(statuses),
            )
        )
        if setor_id:
            stmt = stmt.where(ProducaoItemORM.setor_id == setor_id)
        stmt = stmt.order_by(
            ProducaoItemORM.prioridade.desc(),
            ProducaoItemORM.criado_em,
            ProducaoItemORM.id,
        )
        return tuple((_producao(p), _setor(s)) for p, s in self.session.execute(stmt))

    def evento_por_chave(
        self, tenant_id: str, unidade_id: str, idempotency_key: str
    ) -> EventoProducaoORM | None:
        return self.session.scalar(
            select(EventoProducaoORM).where(
                EventoProducaoORM.tenant_id == tenant_id,
                EventoProducaoORM.unidade_id == unidade_id,
                EventoProducaoORM.idempotency_key == idempotency_key,
            )
        )

    def aplicar_transicao(
        self,
        *,
        atual: ProducaoItem,
        destino: str,
        instante: datetime,
        responsavel_id: str,
        event_id: str,
        event_type: str,
        correlation_id: str,
        causation_id: str | None,
        idempotency_key: str,
        payload: dict[str, Any],
    ) -> ProducaoItem:
        valores: dict[str, Any] = {
            "status": destino,
            "versao": atual.versao + 1,
            "atualizado_em": instante,
            "responsavel_id": responsavel_id,
        }
        if destino == "aceita":
            valores["aceita_em"] = instante
        elif destino == "em_preparo":
            if atual.status == "pausada" and atual.pausa_iniciada_em is not None:
                pausa = max(0, int((instante - atual.pausa_iniciada_em).total_seconds()))
                valores["pausa_acumulada_segundos"] = (
                    atual.pausa_acumulada_segundos + pausa
                )
                valores["pausa_iniciada_em"] = None
            if atual.iniciada_em is None:
                valores["iniciada_em"] = instante
        elif destino == "pausada":
            valores["pausa_iniciada_em"] = instante
        elif destino == "pronta":
            valores["pronta_em"] = instante
            if atual.status == "pausada" and atual.pausa_iniciada_em is not None:
                pausa = max(0, int((instante - atual.pausa_iniciada_em).total_seconds()))
                valores["pausa_acumulada_segundos"] = (
                    atual.pausa_acumulada_segundos + pausa
                )
                valores["pausa_iniciada_em"] = None
        elif destino == "retirada":
            valores["retirada_em"] = instante

        resultado = cast(
            CursorResult[Any],
            self.session.execute(
                update(ProducaoItemORM)
                .where(
                    ProducaoItemORM.id == atual.producao_id,
                    ProducaoItemORM.tenant_id == atual.tenant_id,
                    ProducaoItemORM.unidade_id == atual.unidade_id,
                    ProducaoItemORM.versao == atual.versao,
                )
                .values(**valores)
            ),
        )
        if resultado.rowcount != 1:
            raise ErroKDS("producao_concorrente")

        self.session.add(
            EventoProducaoORM(
                event_id=event_id,
                tenant_id=atual.tenant_id,
                unidade_id=atual.unidade_id,
                producao_item_id=atual.producao_id,
                event_type=event_type,
                aggregate_version=atual.versao + 1,
                actor_id=responsavel_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
                idempotency_key=idempotency_key,
                ocorrido_em=instante,
                payload=payload,
            )
        )
        self.session.flush()
        novo = self.obter_producao(atual.tenant_id, atual.unidade_id, atual.producao_id)
        if novo is None:
            raise ErroKDS("producao_indisponivel")
        return novo
