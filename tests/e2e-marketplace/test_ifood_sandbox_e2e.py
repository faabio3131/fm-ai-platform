from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from core.marketplaces.modelos import (
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    StatusPedidoExterno,
)
from core.marketplaces.runtime_teste import RuntimeMarketplaceTeste


def test_fluxo_ifood_sandbox_entrada_saida_reconciliacao() -> None:
    runtime = RuntimeMarketplaceTeste()
    snapshot = PedidoMarketplaceSnapshot(
        id_externo="e2e-order",
        merchant_id="merchant-demo",
        status=StatusPedidoExterno.RECEBIDO,
        total=Decimal("59.90"),
        itens=(
            ItemMarketplace(
                item_id_externo="e2e-item",
                sku="BURGER",
                nome="Combo",
                quantidade=Decimal("1"),
                preco_unitario=Decimal("59.90"),
            ),
        ),
        atualizado_em=datetime.now(timezone.utc),
        versao_externa="1",
    )
    evento_id = runtime.transport.semear_pedido(
        snapshot, evento_id="e2e-event-1"
    )
    entrada = runtime.servico.sincronizar(
        tenant_id="tenant-demo",
        unidade_id="unidade-demo",
        integracao_id="integracao-ifood-demo",
    )
    assert entrada.processados == 1
    assert runtime.transport.foi_reconhecido(evento_id)

    runtime.servico.confirmar(
        tenant_id="tenant-demo",
        unidade_id="unidade-demo",
        integracao_id="integracao-ifood-demo",
        pedido_id_externo="e2e-order",
        idempotency_key="e2e-confirm",
    )
    runtime.servico.publicar_status(
        tenant_id="tenant-demo",
        unidade_id="unidade-demo",
        integracao_id="integracao-ifood-demo",
        pedido_id_externo="e2e-order",
        status=StatusPedidoExterno.PRONTO,
        idempotency_key="e2e-ready",
    )
    atual = runtime.transport.consultar("e2e-order")
    assert atual.status is StatusPedidoExterno.PRONTO

    concluido = replace(
        atual,
        status=StatusPedidoExterno.CONCLUIDO,
        atualizado_em=datetime.now(timezone.utc),
        versao_externa="4",
    )
    runtime.transport.atualizar_snapshot(concluido)
    reconciliado = runtime.servico.reconciliar(
        tenant_id="tenant-demo",
        unidade_id="unidade-demo",
        integracao_id="integracao-ifood-demo",
        pedido_id_externo="e2e-order",
    )
    assert reconciliado.pedido_externo.status_externo is StatusPedidoExterno.CONCLUIDO
    assert len(runtime.dlq.listar()) == 0
