"""Fontes financeiras confiáveis adicionais ao webhook assinado.

Consulta autenticada ao provedor é uma fonte distinta de webhook: ela só pode
liquidar a obrigação quando o provedor retorna explicitamente estado pago e o
pagamento interno pertence ao mesmo provedor/método.
"""

from __future__ import annotations

from datetime import datetime

from core.seguranca.contexto import ContextoExecucao

from .adapters import CobrancaProvedor
from .erros import FonteFinanceiraNaoConfiavel, RecursoPagamentoIndisponivel
from .modelos import MetodoPagamento, ResultadoPagamento
from .repositorios import RepositorioPagamentos
from .servicos import _confirmar_pagamento_validado

_STATUS_PAGOS = frozenset({"pago", "paid", "approved", "aprovado", "autorizado"})


def confirmar_pix_por_consulta_provedor(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    provedor: str,
    cobranca: CobrancaProvedor,
    expected_version: int,
    timestamp: datetime,
) -> ResultadoPagamento | None:
    """Confirma PIX a partir de GET autenticado ao provedor, nunca de input humano."""

    if cobranca.status.strip().casefold() not in _STATUS_PAGOS:
        return None
    pagamento = repositorio.buscar_pagamento(
        contexto.tenant_id, contexto.unidade_id, pagamento_id
    )
    if pagamento is None:
        raise RecursoPagamentoIndisponivel("recurso_indisponivel")
    if pagamento.metodo is not MetodoPagamento.PIX:
        raise FonteFinanceiraNaoConfiavel("consulta PIX aplicada a método incompatível")
    if (pagamento.provedor or "").strip().casefold() != provedor.strip().casefold():
        raise FonteFinanceiraNaoConfiavel("provedor da consulta diverge do pagamento")
    if cobranca.id_externo.strip() == "":
        raise FonteFinanceiraNaoConfiavel("consulta sem referência externa")

    return _confirmar_pagamento_validado(
        contexto=contexto,
        repositorio=repositorio,
        pagamento_id=pagamento_id,
        valor=cobranca.valor,
        metodo=MetodoPagamento.PIX,
        referencia_externa=cobranca.id_externo,
        idempotency_key=(
            f"consulta:{provedor.strip().casefold()}:{cobranca.id_externo}:pago"
        ),
        expected_version=expected_version,
        timestamp=timestamp,
        fonte_financeira_validada=True,
    )



def confirmar_cartao_por_consulta_provedor(
    *,
    contexto: ContextoExecucao,
    repositorio: RepositorioPagamentos,
    pagamento_id: str,
    provedor: str,
    cobranca: CobrancaProvedor,
    expected_version: int,
    timestamp: datetime,
) -> ResultadoPagamento | None:
    """Liquida cartão somente com PAID confirmado em GET autenticado do PSP.

    AUTHORIZED nunca é considerado pagamento liquidado; o redirect do browser
    jamais entra nesta função. O vínculo CHEC_ foi gravado na mesma unidade.
    """
    if cobranca.status.strip().casefold() not in {"pago", "paid"}:
        return None
    if provedor != "pagbank_checkout" or not cobranca.id_externo.startswith("CHEC_"):
        raise FonteFinanceiraNaoConfiavel("referencia de checkout nao confiavel")
    pagamento = repositorio.buscar_pagamento(
        contexto.tenant_id, contexto.unidade_id, pagamento_id
    )
    if pagamento is None:
        raise RecursoPagamentoIndisponivel("recurso_indisponivel")
    if pagamento.metodo not in {
        MetodoPagamento.CARTAO_CREDITO, MetodoPagamento.CARTAO_DEBITO
    }:
        raise FonteFinanceiraNaoConfiavel("checkout cartao aplicado a outro metodo")
    if pagamento.provedor not in (None, "pagbank", "pagbank_checkout"):
        raise FonteFinanceiraNaoConfiavel("provedor da consulta diverge do pagamento")
    if cobranca.valor != pagamento.valor_previsto:
        raise FonteFinanceiraNaoConfiavel("valor liquidado diverge da obrigacao")
    return _confirmar_pagamento_validado(
        contexto=contexto,
        repositorio=repositorio,
        pagamento_id=pagamento_id,
        valor=cobranca.valor,
        metodo=pagamento.metodo,
        referencia_externa=cobranca.id_externo,
        idempotency_key=(
            f"consulta:pagbank_checkout:{cobranca.id_externo}:pago"
        ),
        expected_version=expected_version,
        timestamp=timestamp,
        fonte_financeira_validada=True,
    )
