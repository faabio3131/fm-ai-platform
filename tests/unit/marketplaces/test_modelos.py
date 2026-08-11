from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.modelos import (
    CapacidadeMarketplace,
    CapacidadesMarketplace,
    IntegracaoMarketplace,
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
    hash_payload,
)


def test_capacidades_falham_fechado() -> None:
    capacidades = CapacidadesMarketplace(
        frozenset({CapacidadeMarketplace.RECEBER_PEDIDO})
    )
    assert capacidades.suporta(CapacidadeMarketplace.RECEBER_PEDIDO)
    with pytest.raises(ErroMarketplace, match="capacidade_nao_suportada:cancelar"):
        capacidades.exigir(CapacidadeMarketplace.CANCELAR)


def test_integracao_rejeita_segredo_bruto() -> None:
    with pytest.raises(ErroMarketplace, match="segredo_deve_ser_referencia"):
        IntegracaoMarketplace(
            integracao_id="i",
            tenant_id="t",
            unidade_id="u",
            plataforma=PlataformaMarketplace.IFOOD,
            conta_externa="merchant",
            segredo_ref="Bearer token-real",
            capacidades=CapacidadesMarketplace(frozenset()),
        )


def test_hash_payload_e_deterministico_sem_persistir_conteudo() -> None:
    primeiro = hash_payload({"customerName": "Pessoa", "orderId": "o1"})
    segundo = hash_payload({"orderId": "o1", "customerName": "Pessoa"})
    assert primeiro == segundo
    assert "Pessoa" not in primeiro
    assert len(primeiro) == 64


def test_snapshot_valida_valores_e_timezone() -> None:
    item = ItemMarketplace(
        item_id_externo="item-1",
        sku="SKU1",
        nome="Burger",
        quantidade=Decimal(1),
        preco_unitario=Decimal("32.005"),
    )
    snapshot = PedidoMarketplaceSnapshot(
        id_externo="order-1",
        merchant_id="merchant",
        status=StatusPedidoExterno.RECEBIDO,
        total=Decimal("32.005"),
        itens=(item,),
        atualizado_em=datetime.now(timezone.utc),
    )
    assert snapshot.total == Decimal("32.01")
    assert item.preco_unitario == Decimal("32.01")


def test_snapshot_rejeita_timestamp_naive() -> None:
    item = ItemMarketplace(
        item_id_externo="item-1",
        sku=None,
        nome="Burger",
        quantidade=Decimal(1),
        preco_unitario=Decimal(20),
    )
    with pytest.raises(ErroMarketplace, match="timestamp_sem_timezone"):
        PedidoMarketplaceSnapshot(
            id_externo="order-1",
            merchant_id="merchant",
            status=StatusPedidoExterno.RECEBIDO,
            total=Decimal(20),
            itens=(item,),
            atualizado_em=datetime.now(timezone.utc).replace(tzinfo=None),
        )
