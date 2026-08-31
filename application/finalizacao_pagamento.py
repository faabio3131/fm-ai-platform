"""Compatibilidade PDV após a orquestração canônica de resultado financeiro.

A regra geral de Pedido/Pagamento/VendaFinanceira pertence ao
application.order_result_orchestrator. Este módulo mantém somente projeções
e reconciliação específicas do PDV legado quando existir trabalho pendente dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select

from application.order_result_orchestrator import (
    orquestrar_resultado_pagamento_em_transacao,
)
from application.pdv_legacy_projection import projetar_legado_em_transacao
from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import Pagamento
from core.pdv.adaptadores_sqlalchemy import RepositorioPDVSQLAlchemy
from core.pdv.finalizacao_claim import FINALIZADA, adquirir
from core.pdv.finalizacao_pendente import (
    RepositorioFinalizacaoPendentePDV,
    reconstruir_entrada,
)
from core.pdv.modelos_orm import ReconciliacaoPDVORM
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
    row.estoque_estrategia = "canonico_reservado_aguardando_producao"
    row.cashback_usado = cashback_usado
    row.cashback_ganho = (valor_pedido * Decimal(".05")).quantize(
        Decimal(".01"), rounding=ROUND_HALF_UP
    )
    row.status = "conciliado"
    row.divergencias = []
    recursos.session.flush()


def _resultado_idempotente(pendente) -> ResultadoFinalizacaoPagamento:
    return ResultadoFinalizacaoPagamento(
        True,
        True,
        True,
        pendente.pedido_id,
        pendente.pagamento_id,
        pendente.venda_financeira_id,
        pendente.venda_legada_id,
    )


def finalizar_pagamento_liquidado_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    pagamento: Pagamento,
    timestamp: datetime,
) -> ResultadoFinalizacaoPagamento:
    """Executa a regra geral e, quando aplicável, projeções de compatibilidade PDV."""

    if pagamento.status is not PagamentoStatus.PAGO:
        return ResultadoFinalizacaoPagamento(
            False,
            False,
            pagamento_id=pagamento.id,
        )

    generico = orquestrar_resultado_pagamento_em_transacao(
        recursos=recursos,
        pagamento=pagamento,
        timestamp=timestamp,
    )
    if not generico.finalizado or generico.pedido_id is None:
        return ResultadoFinalizacaoPagamento(
            generico.aplicavel,
            False,
            generico.idempotente,
            generico.pedido_id,
            pagamento.id,
            generico.venda_financeira_id,
            None,
        )
    if generico.venda_financeira_id is None:
        raise FinalizacaoPagamentoInvalida("venda_financeira_ausente")

    pendencias = RepositorioFinalizacaoPendentePDV(recursos.session)
    pendente = pendencias.buscar_por_pagamento(
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        pagamento_id=pagamento.id,
        bloquear=True,
    )
    if pendente is None:
        return ResultadoFinalizacaoPagamento(
            True,
            True,
            generico.idempotente,
            generico.pedido_id,
            pagamento.id,
            generico.venda_financeira_id,
            None,
        )
    if pendencias.finalizada(pendente):
        return _resultado_idempotente(pendente)

    if not adquirir(recursos.session, pendente):
        if pendente.status == FINALIZADA:
            return _resultado_idempotente(pendente)
        raise FinalizacaoPagamentoInvalida("finalizacao_em_processamento")

    if pendente.pedido_id != generico.pedido_id:
        raise FinalizacaoPagamentoInvalida("pendencia_pdv_de_outro_pedido")

    entrada = reconstruir_entrada(pendente)
    reserva = recursos.estoque.buscar_reserva(
        pagamento.tenant_id,
        pagamento.unidade_id,
        generico.pedido_id,
    )
    venda_legada_id = projetar_legado_em_transacao(
        recursos=recursos,
        tenant_id=pagamento.tenant_id,
        unidade_id=pagamento.unidade_id,
        pedido_id=generico.pedido_id,
        entrada=entrada,
        reserva=reserva,
        timestamp=timestamp,
        projetar_estoque=False,
    )
    RepositorioPDVSQLAlchemy(recursos.session).criar_link(
        tenant=pagamento.tenant_id,
        unidade=pagamento.unidade_id,
        pedido_id=generico.pedido_id,
        venda_financeira_id=generico.venda_financeira_id,
        venda_legada_id=venda_legada_id,
        instante=timestamp,
    )
    _atualizar_reconciliacao(
        recursos=recursos,
        chave=f"{entrada.idempotency_key}:reconciliacao",
        pagamento=pagamento,
        pedido_id=generico.pedido_id,
        venda_financeira_id=generico.venda_financeira_id,
        venda_legada_id=venda_legada_id,
        valor_pedido=entrada.total.valor,
        cashback_usado=(
            entrada.desconto_cashback.valor
            if entrada.usar_cashback
            else Decimal(0)
        ),
    )
    pendencias.marcar_finalizada(
        pendente,
        venda_financeira_id=generico.venda_financeira_id,
        venda_legada_id=venda_legada_id,
        instante=timestamp,
    )
    return ResultadoFinalizacaoPagamento(
        True,
        True,
        generico.idempotente,
        generico.pedido_id,
        pagamento.id,
        generico.venda_financeira_id,
        venda_legada_id,
    )
