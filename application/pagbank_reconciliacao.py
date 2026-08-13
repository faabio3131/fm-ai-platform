"""Reconciliação PagBank por consulta autenticada ao provedor."""

from __future__ import annotations

from datetime import datetime

from application.finalizacao_pagamento import finalizar_pagamento_liquidado_em_transacao
from core.pagamentos.fontes_financeiras import confirmar_pix_por_consulta_provedor
from core.pagamentos.modelos import ResultadoPagamento, TipoTransacao
from core.pagamentos.pagbank import AdapterPagBank
from core.seguranca.contexto import ContextoExecucao
from infra.transacoes.uow import RecursosTransacionaisV1


class ReconciliacaoPagBankInvalida(RuntimeError):
    pass


def reconciliar_order_pagbank_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    adapter: AdapterPagBank,
    order_id: str,
    timestamp: datetime,
) -> ResultadoPagamento | None:
    """Consulta um ORDE já vinculado e confirma apenas se o PagBank disser pago."""

    vinculo = recursos.pagamentos.buscar_transacao_externa(
        "pagbank", order_id, TipoTransacao.INICIACAO
    )
    if vinculo is None:
        return None

    pagamento = recursos.pagamentos.buscar_pagamento(
        vinculo.tenant_id, vinculo.unidade_id, vinculo.pagamento_id
    )
    if pagamento is None:
        raise ReconciliacaoPagBankInvalida("vínculo externo sem pagamento interno")

    cobranca = adapter.consultar_transacao(order_id)
    if cobranca is None:
        return None

    contexto = ContextoExecucao.sistema(
        identidade="pagbank-reconciliacao",
        motivo="consulta autenticada ao PagBank para reconciliacao financeira",
        tenant_id=vinculo.tenant_id,
        unidade_id=vinculo.unidade_id,
        correlation_id=vinculo.correlation_id,
        solicitado_em=timestamp,
    )
    resultado = confirmar_pix_por_consulta_provedor(
        contexto=contexto,
        repositorio=recursos.pagamentos,
        pagamento_id=vinculo.pagamento_id,
        provedor="pagbank",
        cobranca=cobranca,
        expected_version=pagamento.versao,
        timestamp=timestamp,
    )
    if resultado is not None and not resultado.idempotente:
        recursos.registrar_efeitos(
            eventos=resultado.eventos,
            auditorias=resultado.auditorias,
        )
    if resultado is not None:
        finalizar_pagamento_liquidado_em_transacao(
            recursos=recursos,
            pagamento=resultado.pagamento,
            timestamp=timestamp,
        )
    return resultado
