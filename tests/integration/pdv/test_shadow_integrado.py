from sqlalchemy import func, select

from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pdv.modelos_orm import ReconciliacaoPDVORM
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar


def test_shadow_real_sem_segundo_efeito(fabrica, contexto, entrada):
    executar(fabrica, contexto, entrada, ModoPDV.SHADOW)
    executar(fabrica, contexto, entrada, ModoPDV.SHADOW)
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert s.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert s.scalar(select(func.count()).select_from(PagamentoORM)) == 0
        assert s.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
        assert s.get(InsumoTeste, 1).saldo_atual == 9
        assert s.get(ClienteTeste, 1).saldo_cashback == 6.25
        assert s.scalar(select(ReconciliacaoPDVORM.status)) == "conciliado"
