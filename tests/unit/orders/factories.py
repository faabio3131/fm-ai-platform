from dataclasses import replace
from datetime import datetime, timezone

from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import (
    AdicionalItemPedido,
    ItemPedido,
    ObservacaoPedido,
    Pedido,
)
from core.dominio.tipos import QuantidadeItem


AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)


def pedido(**mudancas):
    tenant, unidade = TenantId("tenant-a"), UnidadeId("unidade-a")
    adicional = AdicionalItemPedido(
        id="adc-1",
        tenant_id=tenant,
        unidade_id=unidade,
        nome="Bacon",
        quantidade=QuantidadeItem(1),
        preco_unitario=Dinheiro("2.00"),
        subtotal=Dinheiro("2.00"),
    )
    item = ItemPedido(
        id=PedidoItemId("item-1"),
        tenant_id=tenant,
        unidade_id=unidade,
        produto_id=ProdutoId("produto-que-pode-mudar"),
        nome_produto="X-Burger snapshot",
        quantidade=QuantidadeItem(2),
        preco_unitario=Dinheiro("10.00"),
        subtotal=Dinheiro("22.00"),
        observacao="Sem cebola",
        ficha_versao="ficha-v3",
        adicionais=(adicional,),
    )
    base = Pedido(
        id=PedidoId("pedido-1"),
        tenant_id=tenant,
        unidade_id=unidade,
        origem=OrigemPedido.BALCAO,
        canal=CanalAtendimento.PRESENCIAL,
        status=PedidoStatus.RASCUNHO,
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=CorrelationId("corr-1"),
        idempotency_key=IdempotencyKey("idem-1"),
        subtotal=Dinheiro("22.00"),
        descontos=Dinheiro("1.00"),
        taxas=Dinheiro("3.00"),
        total=Dinheiro("24.00"),
        itens=(item,),
        observacoes=(
            ObservacaoPedido(
                id="obs-1",
                tenant_id=tenant,
                unidade_id=unidade,
                texto="Entregar no balcao",
                criado_em=AGORA,
            ),
        ),
    )
    return replace(base, **mudancas)
