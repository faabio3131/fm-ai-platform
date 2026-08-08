from decimal import Decimal

from sqlalchemy import func, select

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
from core.pedidos.modelos_orm import EventoPedidoPersistidoORM, PedidoORM

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_canary_dinheiro_pr7_e_retry_exatamente_uma_vez(fabrica, contexto, entrada):
    resultado = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    repetido = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    assert resultado.sucesso and repetido.sucesso
    assert resultado.troco.valor == Decimal("25.10")
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert (
            s.scalar(select(func.count()).select_from(EventoPedidoPersistidoORM)) == 2
        )
        assert s.scalar(select(func.count()).select_from(ObrigacaoPagamentoORM)) == 1
        assert s.scalar(select(func.count()).select_from(PagamentoORM)) == 1
        assert (
            s.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(TransacaoPagamentoORM.tipo == "confirmacao")
            )
            == 1
        )
        assert s.scalar(select(func.count()).select_from(CriterioFinanceiroORM)) == 1
        assert s.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert s.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert s.scalar(select(func.count()).select_from(VendaLegadaLinkORM)) == 1
        assert s.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 4
        assert s.scalar(select(func.count()).select_from(ReconciliacaoPDVORM)) == 1
        assert Decimal(str(s.get(VendaTeste, 1).valor_total)) == Decimal("24.9")
        assert s.get(InsumoTeste, 1).saldo_atual == 9
        assert Decimal(str(s.get(ClienteTeste, 1).saldo_cashback)) == Decimal("6.25")
