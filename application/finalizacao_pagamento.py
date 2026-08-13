"""Finalização canônica após liquidação eletrônica confiável."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from application.pdv_legacy_projection import projetar_legado_em_transacao
from core.dominio.enums import PagamentoStatus, PedidoStatus
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.estoque.modelos import StatusReserva
from core.estoque.servicos import consumir_reserva
from core.pagamentos.modelos import Pagamento
from core.pagamentos.servicos import avaliar_criterio_financeiro, reconhecer_venda
from core.pdv.adaptadores_sqlalchemy import RepositorioPDVSQLAlchemy
from core.pdv.finalizacao_pendente import (
    RepositorioFinalizacaoPendentePDV,
    reconstruir_entrada,
)
from core.pdv.modelos_orm import ReconciliacaoPDVORM
from core.pedidos.servicos import transicionar_pedido
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1


class FinalizacaoPagamentoInvalida(RuntimeError):
    pass


@dataclass(frozen=True)
class ResultadoFinalizacaoPagamento:
    aplicavel: bool
    finalizada: bool
    idempotente: bool = False
    pedido_id: str | None = None
    pagamento_id: str | None = None
    venda_financeira_id: str | None = None
    venda_legada_id: str | None = None


def _fingerprint(*valores: object) -> str:
    return hashlib.sha256(
        json.dumps(valores, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _contexto(pagamento: Pagamento, timestamp: datetime) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="pagamento-finalizador-v1",
        motivo="efeitos derivados de pagamento eletrônico liquidado por fonte confiável",
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        correlation_id=pagamento.correlation_id,
        solicitado_em=timestamp,
    )


def _atualizar_reconciliacao(
    *,
    recursos: RecursosTransacionaisV1,
    chave: str,
    pagamento: Pagamento,
    pedido_id: str,
    venda_financeira_id: str,
    venda_legada_id: str,
    valor_pedido: Decimal,
    cashback_usado: Decimal,
) -> None:
    row = recursos.session.scalar(
        select(ReconciliacaoPDVORM).where(
            ReconciliacaoPDVORM.tenant_id == pagamento.tenant_id,
            ReconciliacaoPDVORM.unidade_id == pagamento.unidade_id,
            ReconciliacaoPDVORM.idempotency_key == chave,
        )
    )
    if row is None:
        return
    row.pedido_id = pedido_id
    row.pagamento_id = pagamento.id
    row.venda_financeira_id = venda_financeira_id
    row.venda_legada_id = venda_legada_id
    row.valor_pagamento = pagamento.valor_pago.valor
    row.valor_venda_financeira = pagamento.valor_pago.valor
    row.valor_venda_legada = valor_pedido
    row.estoque_estrategia = "canonico_autoritativo_legado_projecao"
    row.cashback_usado = cashback_usado
    row.cashback_ganho = (valor_pedido * Decimal("0.05")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    row.status = "conciliado"
    row.divergencias = []
    recursos.session.flush()


def finalizar_pagamento_liquidado_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    pagamento: Pagamento,
    timestamp: datetime,
) -> ResultadoFinalizacaoPagamento:
    """Conclui trabalho PDV pendente; o chamador continua dono do commit."""

    if pagamento.status is not PagamentoStatus.PAGO:
        return ResultadoFinalizacaoPagamento(False, False, pagamento_id=pagamento.id)

    pendencias = RepositorioFinalizacaoPendentePDV(recursos.session)
    pendente = pendencias.buscar_por_pagamento(
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        pagamento_id=pagamento.id,
        bloquear=True,
    )
    if pendente is None:
        return ResultadoFinalizacaoPagamento(False, False, pagamento_id=pagamento.id)
    if pendencias.finalizada(pendente):
        return ResultadoFinalizacaoPagamento(
            True,
            True,
            True,
            pendente.pedido_id,
            pendente.pagamento_id,
            pendente.venda_financeira_id,
            pendente.venda_legada_id,
        )

    entrada = reconstruir_entrada(pendente)
    contexto = _contexto(pagamento, timestamp)
    pedido = recursos.pedidos.buscar(
        TenantId(pagamento.tenant_id),
        UnidadeId(pagamento.unidade_id),
        PedidoId(pendente.pedido_id),
    )
    if pedido is None or pagamento.pedido_id != str(pedido.id):
        raise FinalizacaoPagamentoInvalida("pagamento sem pedido compatível")

    posteriores = {
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
    if pedido.status is PedidoStatus.AGUARDANDO_CONFIRMACAO:
        pedido = transicionar_pedido(
            tenant_id=pedido.tenant_id,
            unidade_id=pedido.unidade_id,
            pedido_id=pedido.id,
            destino=PedidoStatus.CONFIRMADO,
            versao_esperada=pedido.versao,
            idempotency_key=IdempotencyKey(
                f"{entrada.idempotency_key}:pedido:confirmado"
            ),
            contexto=contexto,
            repositorio=recursos.pedidos,
            outbox=recursos.outbox,
            auditoria=recursos.auditoria,
            timestamp=timestamp,
            precondicoes={"dados_confirmados": True},
            metadata={"canal": "pdv", "pagamento": "confirmado_assincrono"},
        ).pedido
    elif pedido.status not in posteriores:
        raise FinalizacaoPagamentoInvalida(
            f"pedido não finalizável: {pedido.status.value}"
        )

    reserva = recursos.estoque.buscar_reserva(
        pagamento.tenant_id, pagamento.unidade_id, str(pedido.id)
    )
    if reserva is not None and reserva.status is StatusReserva.ATIVA:
        consumido = consumir_reserva(
            contexto=contexto,
            repositorio=recursos.estoque,
            pedido_id=str(pedido.id),
            pedido_version=pedido.versao,
            idempotency_key=f"{entrada.idempotency_key}:estoque:consumo",
        )
        if not consumido.idempotente:
            recursos.registrar_efeitos(
                eventos=consumido.eventos, auditorias=consumido.auditorias
            )
    elif reserva is not None and reserva.status is StatusReserva.LIBERADA:
        raise FinalizacaoPagamentoInvalida("reserva de estoque já liberada")

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
        f"{entrada.idempotency_key}:criterio",
        _fingerprint(
            str(pedido.id), pagamento.id, criterio.codigo, criterio.valor_reconhecivel.valor
        ),
    )
    reconhecida = reconhecer_venda(
        contexto=contexto,
        repositorio=recursos.pagamentos,
        criterio=criterio,
        metodo=pagamento.metodo,
        idempotency_key=f"{entrada.idempotency_key}:venda",
        timestamp=timestamp,
        produto_id_legado=entrada.produto_id,
    )
    if not reconhecida.idempotente:
        recursos.registrar_efeitos(
            eventos=(reconhecida.evento,), auditorias=(reconhecida.auditoria,)
        )

    venda_legada_id = projetar_legado_em_transacao(
        recursos=recursos,
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        pedido_id=str(pedido.id),
        entrada=entrada,
        reserva=reserva,
        timestamp=timestamp,
    )
    RepositorioPDVSQLAlchemy(recursos.session).criar_link(
        tenant=pagamento.tenant_id,
        unidade=pagamento.unidade_id,
        pedido_id=str(pedido.id),
        venda_financeira_id=reconhecida.venda.id,
        venda_legada_id=venda_legada_id,
        instante=timestamp,
    )
    _atualizar_reconciliacao(
        recursos=recursos,
        chave=f"{entrada.idempotency_key}:reconciliacao",
        pagamento=pagamento,
        pedido_id=str(pedido.id),
        venda_financeira_id=reconhecida.venda.id,
        venda_legada_id=venda_legada_id,
        valor_pedido=entrada.total.valor,
        cashback_usado=(
            entrada.desconto_cashback.valor if entrada.usar_cashback else Decimal(0)
        ),
    )
    pendencias.marcar_finalizada(
        pendente,
        venda_financeira_id=reconhecida.venda.id,
        venda_legada_id=venda_legada_id,
        instante=timestamp,
    )
    return ResultadoFinalizacaoPagamento(
        True,
        True,
        False,
        str(pedido.id),
        pagamento.id,
        reconhecida.venda.id,
        venda_legada_id,
    )
