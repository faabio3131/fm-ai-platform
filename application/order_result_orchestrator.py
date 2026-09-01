"""Orquestração canônica de resultado financeiro independente do canal.

A liquidação confiável de um Pagamento pode confirmar o Pedido e reconhecer a
VendaFinanceira sem depender de PDV, Streamlit, canal ou projeção legada. Estoque
e produção são observados como autoridades próprias: pagamento não consome reserva.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime

from sqlalchemy import inspect, select

from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.estoque.modelos import StatusReserva
from core.kds.modelos_orm import ProducaoItemORM
from core.pagamentos.modelos import Pagamento
from core.pagamentos.servicos import avaliar_criterio_financeiro, reconhecer_venda
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.transacoes.uow import RecursosTransacionaisV1


class OrquestracaoResultadoInvalida(RuntimeError):
    """Estado autoritativo incompatível com a finalização solicitada."""


@dataclass(frozen=True)
class ResultadoOrquestracaoPedido:
    aplicavel: bool
    finalizado: bool
    idempotente: bool
    pedido_id: str | None
    pagamento_id: str
    pedido_status: PedidoStatus | None
    pagamento_status: PagamentoStatus
    venda_financeira_id: str | None
    reserva_status: StatusReserva | None
    producao_status: tuple[str, ...]

    @property
    def producao_iniciada(self) -> bool:
        return any(
            status in {"em_preparo", "pausada", "pronta", "retirada"}
            for status in self.producao_status
        )


def _fingerprint(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(
            valores,
            default=str,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _contexto_resultado(
    pagamento: Pagamento,
    timestamp: datetime,
) -> ContextoExecucao:
    tecnico = ContextoExecucao.sistema(
        identidade="order-result-orchestrator-v1",
        motivo="efeitos derivados de resultado financeiro autoritativo",
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        correlation_id=pagamento.correlation_id,
        solicitado_em=timestamp,
    )
    return replace(
        tecnico,
        permissoes=frozenset(
            {
                Permissao.PEDIDO_ALTERAR,
                Permissao.PAGAMENTO_CONFIRMAR,
            }
        ),
    )


def _producao_status(
    recursos: RecursosTransacionaisV1,
    *,
    tenant_id: str,
    unidade_id: str,
    pedido_id: str,
) -> tuple[str, ...]:
    connection = recursos.session.connection()
    if not inspect(connection).has_table(ProducaoItemORM.__tablename__):
        # Produção é estado observado, não pré-requisito da finalização financeira.
        # O runtime KDS continua responsável por falhar fechado em seus próprios writes.
        return ()
    statuses = recursos.session.scalars(
        select(ProducaoItemORM.status).where(
            ProducaoItemORM.tenant_id == tenant_id,
            ProducaoItemORM.unidade_id == unidade_id,
            ProducaoItemORM.pedido_id == pedido_id,
        )
    ).all()
    return tuple(sorted({str(status) for status in statuses}))


def _snapshot_estado(
    recursos: RecursosTransacionaisV1,
    *,
    pagamento: Pagamento,
    pedido,
    venda_financeira_id: str | None,
    idempotente: bool,
    finalizado: bool,
) -> ResultadoOrquestracaoPedido:
    reserva = recursos.estoque.buscar_reserva(
        pagamento.tenant_id,
        pagamento.unidade_id,
        str(pedido.id),
    )
    return ResultadoOrquestracaoPedido(
        aplicavel=True,
        finalizado=finalizado,
        idempotente=idempotente,
        pedido_id=str(pedido.id),
        pagamento_id=pagamento.id,
        pedido_status=pedido.status,
        pagamento_status=pagamento.status,
        venda_financeira_id=venda_financeira_id,
        reserva_status=reserva.status if reserva is not None else None,
        producao_status=_producao_status(
            recursos,
            tenant_id=pagamento.tenant_id,
            unidade_id=pagamento.unidade_id,
            pedido_id=str(pedido.id),
        ),
    )


def orquestrar_resultado_pagamento_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    pagamento: Pagamento,
    timestamp: datetime,
) -> ResultadoOrquestracaoPedido:
    """Converge Pagamento -> Pedido -> VendaFinanceira, sem efeitos prematuros.

    O chamador permanece dono de commit/rollback. Reserva de estoque continua
    ativa até o marco real de produção; KDS/expedição continuam autoridades dos
    seus próprios estados.
    """

    pedido = recursos.pedidos.buscar(
        TenantId(pagamento.tenant_id),
        UnidadeId(pagamento.unidade_id),
        PedidoId(pagamento.pedido_id),
    )
    if pedido is None:
        raise OrquestracaoResultadoInvalida("pagamento_sem_pedido_canonico")
    if pagamento.pedido_id != str(pedido.id):
        raise OrquestracaoResultadoInvalida("pagamento_pedido_divergente")

    if pagamento.status is not PagamentoStatus.PAGO:
        return _snapshot_estado(
            recursos,
            pagamento=pagamento,
            pedido=pedido,
            venda_financeira_id=None,
            idempotente=True,
            finalizado=False,
        )

    estados_posteriores = {
        PedidoStatus.CONFIRMADO,
        PedidoStatus.ENVIADO_PRODUCAO,
        PedidoStatus.EM_PREPARO,
        PedidoStatus.PRONTO,
        PedidoStatus.EM_EXPEDICAO,
        PedidoStatus.SAIU_ENTREGA,
        PedidoStatus.SERVIDO,
        PedidoStatus.ENTREGUE,
        PedidoStatus.CONCLUIDO,
    }
    contexto = _contexto_resultado(pagamento, timestamp)
    pedido_idempotente = True

    if pedido.status is PedidoStatus.AGUARDANDO_CONFIRMACAO:
        confirmado = transicionar_pedido(
            tenant_id=pedido.tenant_id,
            unidade_id=pedido.unidade_id,
            pedido_id=pedido.id,
            destino=PedidoStatus.CONFIRMADO,
            versao_esperada=pedido.versao,
            idempotency_key=IdempotencyKey(
                f"order-result:{pagamento.id}:pedido:confirmado"
            ),
            contexto=contexto,
            repositorio=recursos.pedidos,
            outbox=recursos.outbox,
            auditoria=recursos.auditoria,
            timestamp=timestamp,
            precondicoes={"dados_confirmados": True},
            metadata={
                "origem_derivada": "resultado_financeiro",
                "canal": pedido.canal.value,
                "pagamento_id": pagamento.id,
            },
        )
        pedido = confirmado.pedido
        pedido_idempotente = confirmado.idempotente
    elif pedido.status not in estados_posteriores:
        raise OrquestracaoResultadoInvalida(
            f"pedido_nao_finalizavel:{pedido.status.value}"
        )

    criterio = avaliar_criterio_financeiro(
        contexto=contexto,
        pagamento=pagamento,
        pedido_id=str(pedido.id),
        timestamp=timestamp,
    )
    criterio = recursos.pagamentos.salvar_criterio(
        pagamento.tenant_id,
        pagamento.unidade_id,
        criterio,
        f"order-result:{pagamento.id}:criterio",
        _fingerprint(
            str(pedido.id),
            pagamento.id,
            criterio.codigo,
            criterio.valor_reconhecivel.valor,
        ),
    )
    reconhecida = reconhecer_venda(
        contexto=contexto,
        repositorio=recursos.pagamentos,
        criterio=criterio,
        metodo=pagamento.metodo,
        idempotency_key=f"order-result:{pagamento.id}:venda",
        timestamp=timestamp,
    )
    if not reconhecida.idempotente:
        recursos.registrar_efeitos(
            eventos=(reconhecida.evento,),
            auditorias=(reconhecida.auditoria,),
        )

    return _snapshot_estado(
        recursos,
        pagamento=pagamento,
        pedido=pedido,
        venda_financeira_id=reconhecida.venda.id,
        idempotente=pedido_idempotente and reconhecida.idempotente,
        finalizado=True,
    )
