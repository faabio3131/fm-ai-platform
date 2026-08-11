from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.ifood_sandbox import (
    IFOOD_ACK_PATH,
    IFOOD_CAPACIDADES,
    IFOOD_EVENTS_BASE_URL,
    IFOOD_POLLING_PATH,
    IfoodSandboxAdapter,
    IfoodSandboxTransport,
)
from core.marketplaces.modelos import (
    CapacidadeMarketplace,
    IntegracaoMarketplace,
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)


def _integracao() -> IntegracaoMarketplace:
    return IntegracaoMarketplace(
        integracao_id="int",
        tenant_id="t",
        unidade_id="u",
        plataforma=PlataformaMarketplace.IFOOD,
        conta_externa="merchant",
        segredo_ref="vault://ifood/test",
        capacidades=IFOOD_CAPACIDADES,
    )


def _snapshot(status: StatusPedidoExterno = StatusPedidoExterno.RECEBIDO):
    return PedidoMarketplaceSnapshot(
        id_externo="order-1",
        merchant_id="merchant",
        status=status,
        total=Decimal(25),
        itens=(
            ItemMarketplace(
                item_id_externo="i1",
                sku="SKU",
                nome="Item",
                quantidade=Decimal(1),
                preco_unitario=Decimal(25),
            ),
        ),
        atualizado_em=datetime.now(timezone.utc),
        versao_externa="1",
    )


def test_constantes_documentam_contrato_oficial_de_eventos() -> None:
    assert IFOOD_EVENTS_BASE_URL.startswith("https://merchant-api.ifood.com.br")
    assert IFOOD_POLLING_PATH == "/events:polling"
    assert IFOOD_ACK_PATH == "/events/acknowledgment"


def test_polling_normaliza_campos_e_ack_e_separado() -> None:
    transport = IfoodSandboxTransport()
    evento_id = transport.semear_pedido(_snapshot(), codigo="PLC", evento_id="evt-1")
    adapter = IfoodSandboxAdapter(transport)
    eventos = adapter.receber_eventos(_integracao())
    assert len(eventos) == 1
    evento = eventos[0]
    assert evento.evento_id == "evt-1"
    assert evento.pedido_id_externo == "order-1"
    assert evento.merchant_id == "merchant"
    assert evento.status is StatusPedidoExterno.RECEBIDO
    assert not transport.foi_reconhecido(evento_id)
    adapter.reconhecer_eventos(_integracao(), (evento_id,))
    assert transport.foi_reconhecido(evento_id)


def test_codigos_principais_sao_traduzidos() -> None:
    transport = IfoodSandboxTransport()
    snapshot = _snapshot(StatusPedidoExterno.CONCLUIDO)
    transport.atualizar_snapshot(snapshot)
    for indice, (codigo, esperado) in enumerate(
        (
            ("CFM", StatusPedidoExterno.CONFIRMADO),
            ("RTP", StatusPedidoExterno.PRONTO),
            ("DSP", StatusPedidoExterno.DESPACHADO),
            ("CON", StatusPedidoExterno.CONCLUIDO),
            ("CAN", StatusPedidoExterno.CANCELADO),
        ),
        start=1,
    ):
        transport.emitir_evento(
            pedido_id="order-1",
            merchant_id="merchant",
            codigo=codigo,
            evento_id=f"evt-{indice}",
        )
    eventos = IfoodSandboxAdapter(transport).receber_eventos(_integracao())
    assert [evento.status for evento in eventos] == [
        StatusPedidoExterno.CONFIRMADO,
        StatusPedidoExterno.PRONTO,
        StatusPedidoExterno.DESPACHADO,
        StatusPedidoExterno.CONCLUIDO,
        StatusPedidoExterno.CANCELADO,
    ]


def test_ifood_v1_nao_improvisa_rejeicao() -> None:
    adapter = IfoodSandboxAdapter(IfoodSandboxTransport())
    assert not adapter.capacidades.suporta(CapacidadeMarketplace.REJEITAR)
    with pytest.raises(ErroMarketplace, match="capacidade_nao_suportada:rejeitar"):
        adapter.rejeitar(
            _integracao(),
            "order-1",
            motivo="sem estoque",
            idempotency_key="reject-1",
        )
