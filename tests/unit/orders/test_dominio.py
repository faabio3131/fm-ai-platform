from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.dominio.ids import PedidoId, VendaId
from core.pedidos.flags import OrdersFeatureFlags

from .factories import pedido


def test_pedido_multi_item_adicional_observacao_snapshot_e_ordem():
    atual = pedido()
    assert atual.itens[0].nome_produto == "X-Burger snapshot"
    assert atual.itens[0].adicionais[0].nome == "Bacon"
    assert atual.observacoes[0].texto == "Entregar no balcao"
    assert atual.para_dict()["itens"][0]["preco_unitario"]["valor"] == "10.00"


@pytest.mark.parametrize("valor", ["0.01", "29.90", "999999.99"])
def test_decimal_sem_perda(valor):
    assert Dinheiro(valor).valor == Decimal(valor)
    with pytest.raises(Exception):
        Dinheiro(float(valor))


def test_dominio_imutavel_ids_nominais_e_flags_desligadas():
    atual = pedido()
    with pytest.raises(FrozenInstanceError):
        atual.versao = 2
    assert PedidoId("1") != VendaId("1")
    assert OrdersFeatureFlags() == OrdersFeatureFlags(False, False, False)
