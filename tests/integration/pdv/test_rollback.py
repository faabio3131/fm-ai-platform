import pytest
from sqlalchemy import func, select

from core.estoque.modelos_orm import (
    MovimentoEstoqueORM,
    ReservaEstoqueORM,
    SaldoEstoqueORM,
)
from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pdv.modelos_orm import EfeitoCompatPDVORM
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM
from infra.eventos.modelos_orm import OutboxEventoORM
from infra.seguranca.modelos_orm import EventoAuditoriaORM

from .conftest import ClienteTeste, InsumoTeste, VendaTeste
from .helpers import executar

PONTOS = (
    "after_checkout_canonico",
    "after_confirmacao",
    "after_estoque_canonico",
    "after_venda_financeira",
    "after_projecoes_legadas",
    "before_reconciliacao",
    "before_commit",
)


@pytest.mark.parametrize("ponto", PONTOS)
def test_rollback_atomico_em_todos_os_pontos(fabrica, contexto, entrada, ponto):
    def falhar(atual):
        if atual == ponto:
            raise RuntimeError(f"falha:{ponto}")

    with pytest.raises(RuntimeError, match="falha"):
        executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY, falhar)
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(PedidoORM)) == 0
        assert s.scalar(select(func.count()).select_from(PagamentoORM)) == 0
        assert s.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
        assert s.scalar(select(func.count()).select_from(ReservaEstoqueORM)) == 0
        assert s.scalar(select(func.count()).select_from(MovimentoEstoqueORM)) == 0
        assert s.scalar(select(func.count()).select_from(SaldoEstoqueORM)) == 0
        assert s.scalar(select(func.count()).select_from(OutboxEventoORM)) == 0
        assert s.scalar(select(func.count()).select_from(EventoAuditoriaORM)) == 0
        assert s.scalar(select(func.count()).select_from(VendaTeste)) == 0
        assert s.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 0
        assert s.get(InsumoTeste, 1).saldo_atual == 10
        assert s.get(ClienteTeste, 1).saldo_cashback == 10
