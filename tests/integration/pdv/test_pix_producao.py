from dataclasses import replace

from sqlalchemy import func, select

from core.pagamentos.modelos_orm import (
    CriterioFinanceiroORM,
    PagamentoORM,
    TransacaoPagamentoORM,
    VendaFinanceiraORM,
)
from core.pdv.roteamento import ModoPDV

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_pix_producao_sem_webhook_permanece_pendente(fabrica, contexto, entrada):
    pix = replace(
        entrada,
        forma_pagamento="Pix (Gerar QR Code Instantâneo)",
        valor_recebido=None,
        pix_sandbox=False,
        confirmacao_presencial=False,
    )
    resultado = executar(fabrica, contexto, pix, ModoPDV.AUTHORITATIVE_CANARY)
    assert not resultado.sucesso
    assert resultado.motivo == "aguardando_confirmacao_pix"
    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(TransacaoPagamentoORM.tipo == "confirmacao")
            )
            == 0
        )
        assert (
            session.scalar(select(func.count()).select_from(CriterioFinanceiroORM)) == 0
        )
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 0
        assert session.get(InsumoTeste, 1).saldo_atual == 10
        assert session.get(ClienteTeste, 1).saldo_cashback == 10
