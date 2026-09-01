from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from core.dominio.dinheiro import Dinheiro
from core.estoque.modelos_orm import ReservaEstoqueORM, SaldoEstoqueORM
from core.pagamentos.modelos_orm import (
    CriterioFinanceiroORM,
    ObrigacaoPagamentoORM,
    PagamentoORM,
    TransacaoPagamentoORM,
    VendaFinanceiraORM,
)
from core.pdv.modelos_orm import (
    EfeitoCompatPDVORM,
    ReconciliacaoPDVORM,
    VendaLegadaLinkORM,
)
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM
from infra.eventos.modelos_orm import OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def _entrada_saldo_zero(fabrica, entrada):
    with fabrica() as session:
        cliente = session.get(ClienteTeste, 1)
        assert cliente is not None
        cliente.saldo_cashback = 100
        session.commit()
    return replace(
        entrada,
        forma_pagamento="Cartão de Crédito",
        valor_recebido=None,
        usar_cashback=True,
        desconto_cashback=Dinheiro(Decimal("29.90")),
        confirmacao_presencial=True,
    )


def test_saldo_zero_fica_canonico_sem_pagamento_ficticio(
    fabrica, contexto, entrada
):
    zerada = _entrada_saldo_zero(fabrica, entrada)

    resultado = executar(fabrica, contexto, zerada, ModoPDV.AUTHORITATIVE_CANARY)
    repetido = executar(fabrica, contexto, zerada, ModoPDV.AUTHORITATIVE_CANARY)

    assert resultado.sucesso
    assert repetido.sucesso and repetido.idempotente
    assert resultado.pagamento_id is None
    assert resultado.venda_financeira_id is None
    assert resultado.pedido_id is not None
    assert resultado.venda_legada_id is not None
    assert resultado.troco.valor == Decimal("0")

    with fabrica() as session:
        pedido = session.scalar(select(PedidoORM))
        assert pedido is not None and pedido.status == "confirmado"

        assert session.scalar(select(func.count()).select_from(ObrigacaoPagamentoORM)) == 0
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 0
        assert session.scalar(select(func.count()).select_from(TransacaoPagamentoORM)) == 0
        assert session.scalar(select(func.count()).select_from(CriterioFinanceiroORM)) == 0
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0

        reserva = session.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.pedido_id == resultado.pedido_id
            )
        )
        assert reserva is not None and reserva.status == "ativa"
        saldo = session.get(
            SaldoEstoqueORM,
            ("tenant-teste", "unidade-teste", "legacy:insumo:1"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal("10")
        assert Decimal(str(saldo.saldo_reservado)) == Decimal("1")

        venda = session.get(VendaTeste, int(resultado.venda_legada_id))
        assert venda is not None
        assert Decimal(str(venda.valor_total)) == Decimal("0.0")
        assert venda.forma_pagamento == "Cashback"
        assert session.scalar(select(func.count()).select_from(VendaLegadaLinkORM)) == 0

        reconciliacao = session.scalar(select(ReconciliacaoPDVORM))
        assert reconciliacao is not None
        assert reconciliacao.status == "conciliado"
        assert reconciliacao.pagamento_id is None
        assert reconciliacao.venda_financeira_id is None
        assert Decimal(str(reconciliacao.valor_pedido)) == Decimal("0.00")
        assert Decimal(str(reconciliacao.cashback_usado)) == Decimal("29.90")
        assert session.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 3

        cliente = session.get(ClienteTeste, 1)
        assert cliente is not None
        assert Decimal(str(cliente.saldo_cashback)) == Decimal("70.1")
        assert Decimal(str(cliente.total_gasto)) == Decimal("0.0")
        assert session.get(InsumoTeste, 1).saldo_atual == 10


_PONTOS_ROLLBACK_ZERO = (
    "after_checkout_canonico",
    "after_confirmacao_saldo_zero",
    "after_projecoes_legadas",
    "before_reconciliacao",
    "before_commit",
)


@pytest.mark.parametrize("ponto", _PONTOS_ROLLBACK_ZERO)
def test_saldo_zero_rollback_atomico_sem_efeito_financeiro(
    fabrica, contexto, entrada, ponto
):
    zerada = _entrada_saldo_zero(fabrica, entrada)

    def falhar(atual):
        if atual == ponto:
            raise RuntimeError(f"falha:{ponto}")

    with pytest.raises(RuntimeError, match="falha"):
        executar(
            fabrica,
            contexto,
            zerada,
            ModoPDV.AUTHORITATIVE_CANARY,
            falhar,
        )

    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 0
        assert session.scalar(select(func.count()).select_from(ObrigacaoPagamentoORM)) == 0
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 0
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
        assert session.scalar(select(func.count()).select_from(ReservaEstoqueORM)) == 0
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 0
        assert session.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 0
        assert session.scalar(select(func.count()).select_from(ReconciliacaoPDVORM)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEventoORM)) == 0
        assert session.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 0
        cliente = session.get(ClienteTeste, 1)
        assert cliente is not None
        assert Decimal(str(cliente.saldo_cashback)) == Decimal("100.0")
        assert session.get(InsumoTeste, 1).saldo_atual == 10
