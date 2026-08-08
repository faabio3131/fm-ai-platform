from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from core.pagamentos.modelos_orm import (
    CriterioFinanceiroORM,
    ObrigacaoPagamentoORM,
    TransacaoPagamentoORM,
    VendaFinanceiraORM,
)
from core.pdv.modelos_orm import EfeitoCompatPDVORM, VendaLegadaLinkORM
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_duas_sessoes_mesmo_checkout_constraints_impedem_duplicidade(
    fabrica, contexto, entrada
):
    barreira = Barrier(2)

    def worker():
        barreira.wait()
        try:
            return executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
        except Exception as exc:  # SQLite pode recusar um writer concorrente.
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(lambda _: worker(), range(2)))
    assert len(resultados) == 2
    with fabrica() as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert (
            session.scalar(select(func.count()).select_from(ObrigacaoPagamentoORM)) == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(TransacaoPagamentoORM)
                .where(TransacaoPagamentoORM.tipo == "confirmacao")
            )
            == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(CriterioFinanceiroORM)) == 1
        )
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert session.scalar(select(func.count()).select_from(VendaLegadaLinkORM)) == 1
        assert session.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 4
        assert session.get(InsumoTeste, 1).saldo_atual == 9
        assert session.get(ClienteTeste, 1).saldo_cashback == 6.25
