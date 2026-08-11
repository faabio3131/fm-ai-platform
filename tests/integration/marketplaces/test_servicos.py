from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.modelos import (
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    StatusPedidoExterno,
)
from core.marketplaces.runtime_teste import RuntimeMarketplaceTeste

TENANT = "tenant-demo"
UNIDADE = "unidade-demo"
INTEGRACAO = "integracao-ifood-demo"
MERCHANT = "merchant-demo"


def _snapshot(
    *,
    order_id: str = "order-1",
    status: StatusPedidoExterno = StatusPedidoExterno.RECEBIDO,
    atualizado_em: datetime | None = None,
    versao: str = "1",
) -> PedidoMarketplaceSnapshot:
    return PedidoMarketplaceSnapshot(
        id_externo=order_id,
        merchant_id=MERCHANT,
        status=status,
        total=Decimal(40),
        itens=(
            ItemMarketplace(
                item_id_externo="item-1",
                sku="SKU1",
                nome="Burger",
                quantidade=Decimal(1),
                preco_unitario=Decimal(40),
            ),
        ),
        atualizado_em=atualizado_em or datetime.now(timezone.utc),
        versao_externa=versao,
    )


def _sync(runtime: RuntimeMarketplaceTeste):
    return runtime.servico.sincronizar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
    )


def test_inbox_e_persistida_antes_do_ack_e_retry_nao_reconhece() -> None:
    runtime = RuntimeMarketplaceTeste()
    evento_id = runtime.transport.semear_pedido(
        _snapshot(), evento_id="evt-retry"
    )
    runtime.pedidos_internos.falhas_criacao_restantes = 1
    primeiro = _sync(runtime)
    assert primeiro.retry == 1
    assert primeiro.reconhecidos == 0
    assert not runtime.transport.foi_reconhecido(evento_id)
    historico = runtime.inbox.historico()
    assert len(historico) == 1
    assert historico[0].processado_em is None
    segundo = _sync(runtime)
    assert segundo.processados == 1
    assert runtime.transport.foi_reconhecido(evento_id)


def test_evento_duplicado_nao_cria_segundo_pedido() -> None:
    runtime = RuntimeMarketplaceTeste()
    runtime.transport.semear_pedido(_snapshot(), evento_id="evt-dup")
    primeiro = _sync(runtime)
    assert primeiro.processados == 1
    assert len(runtime.pedidos_internos.dados) == 1
    runtime.transport._reconhecidos.clear()
    segundo = _sync(runtime)
    assert segundo.duplicados == 1
    assert len(runtime.pedidos_internos.dados) == 1


def test_evento_de_outra_conta_vai_dlq_e_e_reconhecido() -> None:
    runtime = RuntimeMarketplaceTeste()
    runtime.transport.atualizar_snapshot(_snapshot())
    evento_id = runtime.transport.emitir_evento(
        pedido_id="order-1",
        merchant_id="merchant-invasor",
        codigo="PLC",
        evento_id="evt-idor",
    )
    resultado = _sync(runtime)
    assert resultado.dlq == 1
    assert runtime.transport.foi_reconhecido(evento_id)
    assert len(runtime.dlq.listar()) == 1
    assert len(runtime.pedidos_internos.dados) == 0


def test_fora_de_ordem_nao_regride_e_reconcilia_snapshot_atual() -> None:
    runtime = RuntimeMarketplaceTeste()
    t0 = datetime.now(timezone.utc)
    recebido = _snapshot(
        status=StatusPedidoExterno.RECEBIDO,
        atualizado_em=t0,
        versao="1",
    )
    runtime.transport.semear_pedido(recebido, evento_id="evt-1", ocorrido_em=t0)
    assert _sync(runtime).processados == 1

    atual = replace(
        recebido,
        status=StatusPedidoExterno.DESPACHADO,
        atualizado_em=t0 + timedelta(minutes=10),
        versao_externa="3",
    )
    runtime.transport.atualizar_snapshot(atual)
    runtime.transport.emitir_evento(
        pedido_id="order-1",
        merchant_id=MERCHANT,
        codigo="DSP",
        evento_id="evt-3",
        ocorrido_em=t0 + timedelta(minutes=10),
        versao_externa="3",
    )
    assert _sync(runtime).processados == 1

    runtime.transport.emitir_evento(
        pedido_id="order-1",
        merchant_id=MERCHANT,
        codigo="CFM",
        evento_id="evt-2-late",
        ocorrido_em=t0 + timedelta(minutes=5),
        versao_externa="2",
    )
    assert _sync(runtime).processados == 1
    pedido = runtime.pedidos_externos.obter(
        integracao_id=INTEGRACAO, id_externo="order-1"
    )
    assert pedido is not None
    assert pedido.status_externo is StatusPedidoExterno.DESPACHADO
    assert pedido.ultima_ocorrencia_em == atual.atualizado_em


def test_reconciliacao_corrige_drift_sem_evento_novo() -> None:
    runtime = RuntimeMarketplaceTeste()
    base = _snapshot()
    runtime.transport.semear_pedido(base, evento_id="evt-base")
    _sync(runtime)
    novo = replace(
        base,
        status=StatusPedidoExterno.CONCLUIDO,
        atualizado_em=base.atualizado_em + timedelta(minutes=20),
        versao_externa="9",
    )
    runtime.transport.atualizar_snapshot(novo)
    resultado = runtime.servico.reconciliar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
        pedido_id_externo="order-1",
    )
    assert resultado.alterado is True
    assert resultado.pedido_externo.status_externo is StatusPedidoExterno.CONCLUIDO


def test_outbox_torna_comando_idempotente() -> None:
    runtime = RuntimeMarketplaceTeste()
    runtime.transport.semear_pedido(_snapshot(), evento_id="evt-out")
    _sync(runtime)
    primeiro = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
        pedido_id_externo="order-1",
        idempotency_key="confirm-1",
    )
    segundo = runtime.servico.confirmar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
        pedido_id_externo="order-1",
        idempotency_key="confirm-1",
    )
    assert primeiro.publicado is True
    assert segundo.idempotente is True
    assert [c for c in runtime.transport.comandos if c[0] == "confirm"] == [
        ("confirm", "order-1", "confirm-1")
    ]


def test_capacidade_publicacao_status_e_cancelamento() -> None:
    runtime = RuntimeMarketplaceTeste()
    runtime.transport.semear_pedido(_snapshot(), evento_id="evt-command")
    _sync(runtime)
    runtime.servico.publicar_status(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
        pedido_id_externo="order-1",
        status=StatusPedidoExterno.PRONTO,
        idempotency_key="ready-1",
    )
    runtime.servico.cancelar(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        integracao_id=INTEGRACAO,
        pedido_id_externo="order-1",
        motivo="solicitacao do cliente",
        idempotency_key="cancel-1",
    )
    assert ("readyToPickup", "order-1", "ready-1") in runtime.transport.comandos
    assert (
        "requestCancellation",
        "order-1",
        "cancel-1",
    ) in runtime.transport.comandos


def test_isolamento_tenant_unidade_fail_closed() -> None:
    runtime = RuntimeMarketplaceTeste()
    with pytest.raises(ErroMarketplace, match="recurso_indisponivel"):
        runtime.servico.sincronizar(
            tenant_id="outro-tenant",
            unidade_id=UNIDADE,
            integracao_id=INTEGRACAO,
        )
    with pytest.raises(ErroMarketplace, match="recurso_indisponivel"):
        runtime.servico.sincronizar(
            tenant_id=TENANT,
            unidade_id="outra-unidade",
            integracao_id=INTEGRACAO,
        )


def test_inbox_nao_persiste_payload_bruto_com_pii() -> None:
    runtime = RuntimeMarketplaceTeste()
    snapshot = _snapshot()
    runtime.transport.atualizar_snapshot(snapshot)
    runtime.transport.emitir_evento(
        pedido_id="order-1",
        merchant_id=MERCHANT,
        codigo="PLC",
        evento_id="evt-pii",
        metadata={"customerName": "Nome Sensivel", "phone": "+551199999999"},
    )
    _sync(runtime)
    envelope = runtime.inbox.historico()[0].mensagem
    serializado = str(envelope.para_dict())
    assert "Nome Sensivel" not in serializado
    assert "+551199999999" not in serializado
    assert "payload_hash" in serializado
