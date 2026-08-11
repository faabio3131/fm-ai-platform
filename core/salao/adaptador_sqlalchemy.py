"""Persistencia SQLAlchemy do salao V1, sempre escopada por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import delete, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from .erros import ErroSalao
from .modelos import (
    Comanda,
    EventoSalao,
    Mesa,
    MetodoFechamento,
    PagamentoConfirmadoComanda,
    ParcelaFechamento,
    ParticipanteComanda,
    PedidoNaComanda,
    StatusComanda,
    StatusMesa,
)
from .modelos_orm import (
    ComandaORM,
    EventoSalaoORM,
    MesaORM,
    PagamentoConfirmadoComandaORM,
    ParcelaFechamentoORM,
    ParticipanteComandaORM,
    PedidoComandaORM,
)


def _utc(valor: Any) -> datetime:
    instante = valor if isinstance(valor, datetime) else datetime.fromisoformat(str(valor))
    return (
        instante.replace(tzinfo=timezone.utc)
        if instante.tzinfo is None
        else instante.astimezone(timezone.utc)
    )


def _mesa(orm: MesaORM) -> Mesa:
    return Mesa(
        mesa_id=orm.id,
        tenant_id=orm.tenant_id,
        unidade_id=orm.unidade_id,
        codigo=orm.codigo,
        nome=orm.nome,
        capacidade=orm.capacidade,
        status=StatusMesa(orm.status),
        posicao_x=Decimal(str(orm.posicao_x)) if orm.posicao_x is not None else None,
        posicao_y=Decimal(str(orm.posicao_y)) if orm.posicao_y is not None else None,
        ativo=orm.ativo,
        versao=orm.versao,
        criado_em=_utc(orm.criado_em),
        atualizado_em=_utc(orm.atualizado_em),
    )


def _comanda(orm: ComandaORM) -> Comanda:
    return Comanda(
        comanda_id=orm.id,
        tenant_id=orm.tenant_id,
        unidade_id=orm.unidade_id,
        mesa_id=orm.mesa_id,
        numero=orm.numero,
        status=StatusComanda(orm.status),
        responsavel_id=orm.responsavel_id,
        aberta_em=_utc(orm.aberta_em),
        fechada_em=_utc(orm.fechada_em) if orm.fechada_em is not None else None,
        total=Decimal(str(orm.total)),
        saldo=Decimal(str(orm.saldo)),
        recebimento_posterior_autorizado=orm.recebimento_posterior_autorizado,
        versao=orm.versao,
    )


class RepositorioSalaoSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar_mesas(self, tenant_id: str, unidade_id: str) -> tuple[Mesa, ...]:
        stmt = (
            select(MesaORM)
            .where(MesaORM.tenant_id == tenant_id, MesaORM.unidade_id == unidade_id)
            .order_by(MesaORM.codigo)
        )
        return tuple(_mesa(item) for item in self.session.scalars(stmt))

    def obter_mesa(self, tenant_id: str, unidade_id: str, mesa_id: str) -> Mesa | None:
        orm = self.session.get(MesaORM, (mesa_id, tenant_id, unidade_id))
        return _mesa(orm) if orm else None

    def criar_mesa(self, mesa: Mesa) -> Mesa:
        existente = self.session.scalar(
            select(MesaORM).where(
                MesaORM.tenant_id == mesa.tenant_id,
                MesaORM.unidade_id == mesa.unidade_id,
                MesaORM.codigo == mesa.codigo,
            )
        )
        if existente:
            atual = _mesa(existente)
            if atual != mesa:
                raise ErroSalao("mesa_codigo_conflitante")
            return atual
        self.session.add(
            MesaORM(
                id=mesa.mesa_id,
                tenant_id=mesa.tenant_id,
                unidade_id=mesa.unidade_id,
                codigo=mesa.codigo,
                nome=mesa.nome,
                capacidade=mesa.capacidade,
                status=mesa.status.value,
                posicao_x=mesa.posicao_x,
                posicao_y=mesa.posicao_y,
                ativo=mesa.ativo,
                versao=mesa.versao,
                criado_em=mesa.criado_em,
                atualizado_em=mesa.atualizado_em,
            )
        )
        self.session.flush()
        return mesa

    def salvar_mesa(self, mesa: Mesa, expected_version: int) -> Mesa:
        resultado = cast(
            CursorResult[Any],
            self.session.execute(
                update(MesaORM)
                .where(
                    MesaORM.id == mesa.mesa_id,
                    MesaORM.tenant_id == mesa.tenant_id,
                    MesaORM.unidade_id == mesa.unidade_id,
                    MesaORM.versao == expected_version,
                )
                .values(
                    status=mesa.status.value,
                    ativo=mesa.ativo,
                    capacidade=mesa.capacidade,
                    nome=mesa.nome,
                    posicao_x=mesa.posicao_x,
                    posicao_y=mesa.posicao_y,
                    versao=mesa.versao,
                    atualizado_em=mesa.atualizado_em,
                )
            ),
        )
        if resultado.rowcount != 1:
            raise ErroSalao("mesa_concorrente")
        self.session.flush()
        return mesa

    def listar_comandas_ativas(
        self, tenant_id: str, unidade_id: str
    ) -> tuple[Comanda, ...]:
        stmt = (
            select(ComandaORM)
            .where(
                ComandaORM.tenant_id == tenant_id,
                ComandaORM.unidade_id == unidade_id,
                ComandaORM.status.notin_([StatusComanda.FECHADA.value, StatusComanda.CANCELADA.value]),
            )
            .order_by(ComandaORM.aberta_em, ComandaORM.numero)
        )
        return tuple(_comanda(item) for item in self.session.scalars(stmt))

    def obter_comanda(
        self, tenant_id: str, unidade_id: str, comanda_id: str
    ) -> Comanda | None:
        orm = self.session.get(ComandaORM, (comanda_id, tenant_id, unidade_id))
        return _comanda(orm) if orm else None

    def criar_comanda(self, comanda: Comanda) -> Comanda:
        existente = self.session.scalar(
            select(ComandaORM).where(
                ComandaORM.tenant_id == comanda.tenant_id,
                ComandaORM.unidade_id == comanda.unidade_id,
                ComandaORM.numero == comanda.numero,
            )
        )
        if existente:
            atual = _comanda(existente)
            if atual != comanda:
                raise ErroSalao("comanda_numero_conflitante")
            return atual
        self.session.add(
            ComandaORM(
                id=comanda.comanda_id,
                tenant_id=comanda.tenant_id,
                unidade_id=comanda.unidade_id,
                mesa_id=comanda.mesa_id,
                numero=comanda.numero,
                status=comanda.status.value,
                responsavel_id=comanda.responsavel_id,
                aberta_em=comanda.aberta_em,
                fechada_em=comanda.fechada_em,
                total=comanda.total,
                saldo=comanda.saldo,
                recebimento_posterior_autorizado=comanda.recebimento_posterior_autorizado,
                versao=comanda.versao,
            )
        )
        self.session.flush()
        return comanda

    def salvar_comanda(self, comanda: Comanda, expected_version: int) -> Comanda:
        resultado = cast(
            CursorResult[Any],
            self.session.execute(
                update(ComandaORM)
                .where(
                    ComandaORM.id == comanda.comanda_id,
                    ComandaORM.tenant_id == comanda.tenant_id,
                    ComandaORM.unidade_id == comanda.unidade_id,
                    ComandaORM.versao == expected_version,
                )
                .values(
                    mesa_id=comanda.mesa_id,
                    status=comanda.status.value,
                    responsavel_id=comanda.responsavel_id,
                    fechada_em=comanda.fechada_em,
                    total=comanda.total,
                    saldo=comanda.saldo,
                    recebimento_posterior_autorizado=comanda.recebimento_posterior_autorizado,
                    versao=comanda.versao,
                )
            ),
        )
        if resultado.rowcount != 1:
            raise ErroSalao("comanda_concorrente")
        self.session.flush()
        return comanda

    def listar_participantes(
        self, tenant_id: str, unidade_id: str, comanda_id: str
    ) -> tuple[ParticipanteComanda, ...]:
        stmt = (
            select(ParticipanteComandaORM)
            .where(
                ParticipanteComandaORM.tenant_id == tenant_id,
                ParticipanteComandaORM.unidade_id == unidade_id,
                ParticipanteComandaORM.comanda_id == comanda_id,
            )
            .order_by(ParticipanteComandaORM.ordem)
        )
        return tuple(
            ParticipanteComanda(
                participante_id=item.id,
                tenant_id=item.tenant_id,
                unidade_id=item.unidade_id,
                comanda_id=item.comanda_id,
                cliente_id=item.cliente_id,
                apelido=item.apelido,
                quota=Decimal(str(item.quota)) if item.quota is not None else None,
                ordem=item.ordem,
            )
            for item in self.session.scalars(stmt)
        )

    def adicionar_participante(self, participante: ParticipanteComanda) -> ParticipanteComanda:
        self.session.add(
            ParticipanteComandaORM(
                id=participante.participante_id,
                tenant_id=participante.tenant_id,
                unidade_id=participante.unidade_id,
                comanda_id=participante.comanda_id,
                cliente_id=participante.cliente_id,
                apelido=participante.apelido,
                quota=participante.quota,
                ordem=participante.ordem,
            )
        )
        self.session.flush()
        return participante

    def mover_participantes(
        self, tenant_id: str, unidade_id: str, origem_id: str, destino_id: str
    ) -> None:
        self.session.execute(
            update(ParticipanteComandaORM)
            .where(
                ParticipanteComandaORM.tenant_id == tenant_id,
                ParticipanteComandaORM.unidade_id == unidade_id,
                ParticipanteComandaORM.comanda_id == origem_id,
            )
            .values(comanda_id=destino_id)
        )
        self.session.flush()

    def listar_pedidos(
        self, tenant_id: str, unidade_id: str, comanda_id: str
    ) -> tuple[PedidoNaComanda, ...]:
        stmt = (
            select(PedidoComandaORM)
            .where(
                PedidoComandaORM.tenant_id == tenant_id,
                PedidoComandaORM.unidade_id == unidade_id,
                PedidoComandaORM.comanda_id == comanda_id,
            )
            .order_by(PedidoComandaORM.criado_em, PedidoComandaORM.id)
        )
        return tuple(
            PedidoNaComanda(
                vinculo_id=item.id,
                tenant_id=item.tenant_id,
                unidade_id=item.unidade_id,
                comanda_id=item.comanda_id,
                pedido_id=item.pedido_id,
                participante_id=item.participante_id,
                valor=Decimal(str(item.valor)),
                criado_em=_utc(item.criado_em),
            )
            for item in self.session.scalars(stmt)
        )

    def vincular_pedido(self, vinculo: PedidoNaComanda) -> PedidoNaComanda:
        existente = self.session.scalar(
            select(PedidoComandaORM).where(
                PedidoComandaORM.tenant_id == vinculo.tenant_id,
                PedidoComandaORM.unidade_id == vinculo.unidade_id,
                PedidoComandaORM.pedido_id == vinculo.pedido_id,
            )
        )
        if existente:
            if existente.comanda_id != vinculo.comanda_id:
                raise ErroSalao("pedido_ja_vinculado")
            return vinculo
        self.session.add(
            PedidoComandaORM(
                id=vinculo.vinculo_id,
                tenant_id=vinculo.tenant_id,
                unidade_id=vinculo.unidade_id,
                comanda_id=vinculo.comanda_id,
                pedido_id=vinculo.pedido_id,
                participante_id=vinculo.participante_id,
                valor=vinculo.valor,
                criado_em=vinculo.criado_em,
            )
        )
        self.session.flush()
        return vinculo

    def mover_pedidos(
        self,
        tenant_id: str,
        unidade_id: str,
        origem_id: str,
        destino_id: str,
        pedido_ids: tuple[str, ...] | None = None,
    ) -> int:
        stmt = update(PedidoComandaORM).where(
            PedidoComandaORM.tenant_id == tenant_id,
            PedidoComandaORM.unidade_id == unidade_id,
            PedidoComandaORM.comanda_id == origem_id,
        )
        if pedido_ids is not None:
            stmt = stmt.where(PedidoComandaORM.pedido_id.in_(pedido_ids))
        resultado = cast(
            CursorResult[Any], self.session.execute(stmt.values(comanda_id=destino_id))
        )
        self.session.flush()
        return int(resultado.rowcount or 0)

    def substituir_parcelas(
        self,
        tenant_id: str,
        unidade_id: str,
        comanda_id: str,
        parcelas: tuple[ParcelaFechamento, ...],
    ) -> None:
        self.session.execute(
            delete(ParcelaFechamentoORM).where(
                ParcelaFechamentoORM.tenant_id == tenant_id,
                ParcelaFechamentoORM.unidade_id == unidade_id,
                ParcelaFechamentoORM.comanda_id == comanda_id,
            )
        )
        for parcela in parcelas:
            self.session.add(
                ParcelaFechamentoORM(
                    id=parcela.parcela_id,
                    tenant_id=tenant_id,
                    unidade_id=unidade_id,
                    comanda_id=comanda_id,
                    participante_id=parcela.participante_id,
                    metodo=parcela.metodo.value,
                    valor=parcela.valor,
                    ordem=parcela.ordem,
                )
            )
        self.session.flush()

    def listar_parcelas(
        self, tenant_id: str, unidade_id: str, comanda_id: str
    ) -> tuple[ParcelaFechamento, ...]:
        stmt = (
            select(ParcelaFechamentoORM)
            .where(
                ParcelaFechamentoORM.tenant_id == tenant_id,
                ParcelaFechamentoORM.unidade_id == unidade_id,
                ParcelaFechamentoORM.comanda_id == comanda_id,
            )
            .order_by(ParcelaFechamentoORM.ordem)
        )
        return tuple(
            ParcelaFechamento(
                parcela_id=item.id,
                comanda_id=item.comanda_id,
                participante_id=item.participante_id,
                metodo=MetodoFechamento(item.metodo),
                valor=Decimal(str(item.valor)),
                ordem=item.ordem,
            )
            for item in self.session.scalars(stmt)
        )

    def registrar_pagamento_confirmado(
        self, registro: PagamentoConfirmadoComanda
    ) -> PagamentoConfirmadoComanda:
        existente = self.session.scalar(
            select(PagamentoConfirmadoComandaORM).where(
                PagamentoConfirmadoComandaORM.tenant_id == registro.tenant_id,
                PagamentoConfirmadoComandaORM.unidade_id == registro.unidade_id,
                PagamentoConfirmadoComandaORM.idempotency_key == registro.idempotency_key,
            )
        )
        if existente:
            if existente.pagamento_id != registro.pagamento_id or Decimal(str(existente.valor)) != registro.valor:
                raise ErroSalao("conflito_idempotencia")
            return registro
        self.session.add(
            PagamentoConfirmadoComandaORM(
                id=registro.registro_id,
                tenant_id=registro.tenant_id,
                unidade_id=registro.unidade_id,
                comanda_id=registro.comanda_id,
                pagamento_id=registro.pagamento_id,
                metodo=registro.metodo.value,
                valor=registro.valor,
                idempotency_key=registro.idempotency_key,
                confirmado_em=registro.confirmado_em,
            )
        )
        self.session.flush()
        return registro

    def total_pago_confirmado(
        self, tenant_id: str, unidade_id: str, comanda_id: str
    ) -> Decimal:
        valor = self.session.scalar(
            select(func.coalesce(func.sum(PagamentoConfirmadoComandaORM.valor), 0)).where(
                PagamentoConfirmadoComandaORM.tenant_id == tenant_id,
                PagamentoConfirmadoComandaORM.unidade_id == unidade_id,
                PagamentoConfirmadoComandaORM.comanda_id == comanda_id,
            )
        )
        return Decimal(str(valor or 0)).quantize(Decimal("0.01"))

    def adicionar_evento(self, evento: EventoSalao) -> EventoSalao:
        existente = self.session.scalar(
            select(EventoSalaoORM).where(
                EventoSalaoORM.tenant_id == evento.tenant_id,
                EventoSalaoORM.unidade_id == evento.unidade_id,
                EventoSalaoORM.idempotency_key == evento.idempotency_key,
            )
        )
        if existente:
            if existente.tipo != evento.tipo or existente.agregado_id != evento.agregado_id:
                raise ErroSalao("conflito_idempotencia")
            return evento
        self.session.add(
            EventoSalaoORM(
                id=evento.evento_id,
                tenant_id=evento.tenant_id,
                unidade_id=evento.unidade_id,
                agregado_tipo=evento.agregado_tipo,
                agregado_id=evento.agregado_id,
                tipo=evento.tipo,
                versao=evento.versao,
                ator_id=evento.ator_id,
                correlation_id=evento.correlation_id,
                idempotency_key=evento.idempotency_key,
                ocorrido_em=evento.ocorrido_em,
                payload_resumo=";".join(f"{k}={v}" for k, v in evento.payload),
            )
        )
        self.session.flush()
        return evento
