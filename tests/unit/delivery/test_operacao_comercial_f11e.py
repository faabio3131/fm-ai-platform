from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from application.delivery_contexto_comercial import ContextoDeliveryComercialV1
from application.delivery_operacao_comercial import _pedido_do_carrinho, _snapshot_endereco
from core.delivery.flags import delivery_v1_access_allowed
from core.delivery.modelos import (
    CarrinhoDelivery,
    CotacaoEntrega,
    ItemCarrinhoDelivery,
    StatusCarrinhoDelivery,
)
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao

_AGORA = datetime(2026, 9, 5, 16, 30, tzinfo=timezone.utc)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-f11e",
        unidade_id="unidade-f11e",
        usuario_id="admin-f11e",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-f11e",
        solicitado_em=_AGORA,
        origem="teste-f11e",
        unidades_permitidas=frozenset({"unidade-f11e"}),
    )


def _carrinho() -> CarrinhoDelivery:
    return CarrinhoDelivery(
        carrinho_id="cart-f11e",
        tenant_id="tenant-f11e",
        unidade_id="unidade-f11e",
        cliente_ref="cliente-f11e",
        versao=3,
        status=StatusCarrinhoDelivery.ABERTO,
        itens=(
            ItemCarrinhoDelivery(
                produto_id="legacy:produto:10",
                nome="Produto comercial",
                quantidade=2,
                preco_unitario=Decimal("25.00"),
                custo_estimado_unitario=Decimal("10.00"),
                produto_versao=1,
            ),
        ),
        endereco=SimpleNamespace(),  # type: ignore[arg-type]
        cotacao=CotacaoEntrega(
            area_id="centro",
            nome_area="Centro",
            taxa=Decimal("7.50"),
            sla_minutos=30,
            sla_maxutos=50,
            versao_area=1,
        ),
        desconto_cupom=Decimal("5.00"),
        cashback_reservado=Decimal("2.00"),
    )


def test_pedido_comercial_preserva_checkout_como_autoridade_economica() -> None:
    pedido = _pedido_do_carrinho(
        carrinho=_carrinho(),
        contexto=_contexto(),
        idempotency_key="idem-f11e",
        timestamp=_AGORA,
    )

    assert pedido.origem is OrigemPedido.DELIVERY_PROPRIO
    assert pedido.canal is CanalAtendimento.DELIVERY_PROPRIO
    assert pedido.status is PedidoStatus.RASCUNHO
    assert str(pedido.cliente_id) == "cliente-f11e"
    assert pedido.subtotal.valor == Decimal("50.00")
    assert pedido.taxas.valor == Decimal("7.50")
    assert pedido.descontos.valor == Decimal("0.00")
    assert pedido.total.valor == Decimal("57.50")
    assert pedido.itens[0].produto_id == "legacy:produto:10"


def test_endereco_comercial_usa_referencia_segura_e_cep_validado() -> None:
    contexto = ContextoDeliveryComercialV1(
        contexto=_contexto(),
        cliente=SimpleNamespace(cliente_id="cliente-f11e"),  # type: ignore[arg-type]
        endereco=SimpleNamespace(
            referencia="address://f11e",
            endereco_formatado="Rua Cliente, 10 - Centro - São Paulo/SP",
            cep="01001000",
        ),  # type: ignore[arg-type]
        catalogo=(),
        origem_entrega=SimpleNamespace(),  # type: ignore[arg-type]
        areas_entrega=(),
    )

    endereco = _snapshot_endereco(contexto)

    assert endereco.endereco_id == "address://f11e"
    assert endereco.cliente_ref == "cliente-f11e"
    assert endereco.cep == "01001000"
    assert endereco.uf == "SP"
    assert endereco.cidade == "São Paulo"


def test_acesso_delivery_exige_cliente_e_pedido_sem_ampliar_alcada() -> None:
    base = {
        Permissao.PEDIDO_CRIAR,
        Permissao.PEDIDO_VISUALIZAR,
        Permissao.CLIENTE_VISUALIZAR,
    }
    assert delivery_v1_access_allowed(base) is True
    assert delivery_v1_access_allowed(base - {Permissao.CLIENTE_VISUALIZAR}) is False
