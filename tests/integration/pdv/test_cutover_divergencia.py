from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from core.estoque.modelos_orm import ReservaEstoqueORM, SaldoEstoqueORM
from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pdv.cutover_canonico import DivergenciaEstoqueCutover
from core.pdv.roteamento import ModoPDV
from core.pedidos.modelos_orm import PedidoORM

from .conftest import InsumoTeste, VendaTeste
from .helpers import executar


def _contar(session, modelo) -> int:
    return session.scalar(select(func.count()).select_from(modelo)) or 0


def test_cutover_bloqueia_segunda_venda_se_estoque_legado_divergir_do_canonico(
    fabrica, contexto, entrada
):
    primeira = executar(fabrica, contexto, entrada, ModoPDV.AUTHORITATIVE_CANARY)
    assert primeira.sucesso

    with fabrica() as session:
        saldo = session.get(
            SaldoEstoqueORM,
            ("tenant-teste", "unidade-teste", "legacy:insumo:1"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal(10)
        insumo = session.get(InsumoTeste, 1)
        assert insumo is not None
        insumo.saldo_atual = 8
        session.commit()

    segunda = replace(entrada, checkout_id="atendimento-divergente")
    with pytest.raises(DivergenciaEstoqueCutover, match="estoque_divergente"):
        executar(fabrica, contexto, segunda, ModoPDV.AUTHORITATIVE_CANARY)

    with fabrica() as session:
        assert _contar(session, PedidoORM) == 1
        assert _contar(session, PagamentoORM) == 1
        assert _contar(session, VendaFinanceiraORM) == 1
        assert _contar(session, ReservaEstoqueORM) == 1
        assert _contar(session, VendaTeste) == 1
        saldo = session.get(
            SaldoEstoqueORM,
            ("tenant-teste", "unidade-teste", "legacy:insumo:1"),
        )
        assert saldo is not None
        assert Decimal(str(saldo.saldo_fisico)) == Decimal(10)
        assert Decimal(str(saldo.saldo_reservado)) == Decimal(1)
        assert session.get(InsumoTeste, 1).saldo_atual == 8
