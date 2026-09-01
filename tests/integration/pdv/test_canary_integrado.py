from decimal import Decimal

from sqlalchemy import func, select

from core.estoque.modelos_orm import (
    MovimentoEstoqueORM,
    ReservaEstoqueORM,
    SaldoEstoqueORM,
)
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
    assert repetido.idempotente is True
    assert resultado.troco.valor == Decimal("25.10")
    with fabrica() as s:
        assert s.scalar(select(func.count()).select_from(PedidoORM)) == 1
        pedido = s.scalar(select(PedidoORM))
        assert pedido is not None
        assert pedido.origem == "pdv"
        assert pedido.canal == "pdv"
        assert pedido.status == "confirmado"
        assert (
            s.scalar(select(func.count()).select_from(EventoPedidoPersistidoORM)) == 3
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
        assert s.scalar(select(func.count()).select_from(MovimentoEstoqueORM)) == 2
        reserva = s.scalar(
            select(ReservaEstoqueORM).where(
                ReservaEstoqueORM.pedido_id == resultado.pedido_id
            )
        )
        assert reserva is not None and reserva.status == "ativa"
        saldo = s.get(
            SaldoEstoqueORM,
            ("tenant-teste", "unidade-teste", "legacy:insumo:1"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal(10)
        assert Decimal(str(saldo.saldo_reservado)) == Decimal(1)
        assert s.scalar(select(func.count()).select_from(VendaTeste)) == 1
        assert s.scalar(select(func.count()).select_from(VendaLegadaLinkORM)) == 1
        assert s.scalar(select(func.count()).select_from(EfeitoCompatPDVORM)) == 3
        assert s.scalar(select(func.count()).select_from(ReconciliacaoPDVORM)) == 1
        assert Decimal(str(s.get(VendaTeste, 1).valor_total)) == Decimal("24.9")
        assert s.get(InsumoTeste, 1).saldo_atual == 10
        assert Decimal(str(s.get(ClienteTeste, 1).saldo_cashback)) == Decimal("6.25")
