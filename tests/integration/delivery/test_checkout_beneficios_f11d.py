from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

import application.delivery_checkout_comercial as modulo
from application.checkout import ComandoCheckoutV1
from application.delivery_checkout_comercial import (
    BeneficioDeliveryObrigatorioIndisponivel,
    PoliticaBeneficiosDeliveryV1,
    executar_checkout_delivery_comercial_em_transacao,
    preparar_checkout_com_beneficios_delivery,
)
from application.delivery_contexto_comercial import ContextoDeliveryComercialV1
from core.delivery.modelos import CarrinhoDelivery, StatusCarrinhoDelivery
from core.dominio.dinheiro import Dinheiro
from core.dominio.enums import CanalAtendimento, OrigemPedido, PedidoStatus
from core.dominio.ids import (
    ClienteId,
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import Pedido
from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao

_AGORA = datetime(2026, 9, 5, 15, 45, tzinfo=timezone.utc)
_TENANT = "tenant-f11d"
_UNIDADE = "unidade-f11d"
_CLIENTE = "cliente-f11d"


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=_TENANT,
        unidade_id=_UNIDADE,
        usuario_id="admin-f11d",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-f11d",
        solicitado_em=_AGORA,
        origem="teste-f11d",
        unidades_permitidas=frozenset({_UNIDADE}),
    )


def _contexto_delivery() -> ContextoDeliveryComercialV1:
    return ContextoDeliveryComercialV1(
        contexto=_contexto(),
        cliente=SimpleNamespace(cliente_id=_CLIENTE),  # type: ignore[arg-type]
        endereco=SimpleNamespace(),  # type: ignore[arg-type]
        catalogo=(),
        origem_entrega=SimpleNamespace(),  # type: ignore[arg-type]
        areas_entrega=(),
    )


def _pedido(*, origem: OrigemPedido = OrigemPedido.DELIVERY_PROPRIO) -> Pedido:
    return Pedido.novo(
        id=PedidoId("pedido-f11d"),
        tenant_id=TenantId(_TENANT),
        unidade_id=UnidadeId(_UNIDADE),
        origem=origem,
        canal=CanalAtendimento.DELIVERY_PROPRIO,
        status=PedidoStatus.RASCUNHO,
        cliente_id=ClienteId(_CLIENTE),
        criado_em=_AGORA,
        atualizado_em=_AGORA,
        versao=1,
        correlation_id=CorrelationId("corr-f11d"),
        idempotency_key=IdempotencyKey("idem-f11d"),
        subtotal=Dinheiro("100.00"),
        descontos=Dinheiro("0.00"),
        taxas=Dinheiro("0.00"),
        total=Dinheiro("100.00"),
    )


def _comando(*, origem: OrigemPedido = OrigemPedido.DELIVERY_PROPRIO) -> ComandoCheckoutV1:
    return ComandoCheckoutV1(
        pedido=_pedido(origem=origem),
        timestamp=_AGORA,
        pagamento_id="pag-f11d",
        metodo_pagamento=MetodoPagamento.PIX,
    )


def _carrinho(
    *, desconto: str = "10.00", cashback: str = "5.00"
) -> CarrinhoDelivery:
    return CarrinhoDelivery(
        carrinho_id="carrinho-f11d",
        tenant_id=_TENANT,
        unidade_id=_UNIDADE,
        cliente_ref=_CLIENTE,
        versao=1,
        status=StatusCarrinhoDelivery.ABERTO,
        desconto_cupom=Decimal(desconto),
        cashback_reservado=Decimal(cashback),
    )


def test_delivery_proprio_e_pagamento_elegivel_aplicam_beneficio() -> None:
    comando, decisao = preparar_checkout_com_beneficios_delivery(
        comando=_comando(),
        contexto_delivery=_contexto_delivery(),
        carrinho=_carrinho(),
    )

    assert decisao.aceito is True
    assert decisao.motivo == "beneficio_aplicado"
    assert decisao.beneficio_total == Decimal("15.00")
    assert comando.pedido.descontos.valor == Decimal("15.00")
    assert comando.pedido.total.valor == Decimal("85.00")
    assert comando.pagamento_id == "pag-f11d"


def test_marketplace_recebe_fallback_neutro_sem_aplicar_beneficio() -> None:
    original = _comando(origem=OrigemPedido.IFOOD)

    comando, decisao = preparar_checkout_com_beneficios_delivery(
        comando=original,
        contexto_delivery=_contexto_delivery(),
        carrinho=_carrinho(),
    )

    assert decisao.aceito is False
    assert decisao.motivo == "origem_nao_elegivel"
    assert comando is original
    assert comando.pedido.total.valor == Decimal("100.00")


def test_metodo_pagamento_inelegivel_recebe_fallback_neutro() -> None:
    original = replace(_comando(), metodo_pagamento=MetodoPagamento.VOUCHER)

    comando, decisao = preparar_checkout_com_beneficios_delivery(
        comando=original,
        contexto_delivery=_contexto_delivery(),
        carrinho=_carrinho(),
    )

    assert decisao.aceito is False
    assert decisao.motivo == "metodo_pagamento_nao_elegivel"
    assert comando is original


def test_beneficio_inativo_ou_indisponivel_nao_quebra_checkout() -> None:
    for politica, motivo in (
        (PoliticaBeneficiosDeliveryV1(ativa=False), "beneficios_inativos"),
        (
            PoliticaBeneficiosDeliveryV1(disponivel=False),
            "beneficios_indisponiveis",
        ),
    ):
        original = _comando()
        comando, decisao = preparar_checkout_com_beneficios_delivery(
            comando=original,
            contexto_delivery=_contexto_delivery(),
            carrinho=_carrinho(),
            politica=politica,
        )
        assert decisao.aceito is False
        assert decisao.motivo == motivo
        assert comando is original


def test_politica_obrigatoria_falha_fechado_quando_beneficio_indisponivel() -> None:
    with pytest.raises(
        BeneficioDeliveryObrigatorioIndisponivel,
        match="beneficios_indisponiveis",
    ):
        preparar_checkout_com_beneficios_delivery(
            comando=_comando(),
            contexto_delivery=_contexto_delivery(),
            carrinho=_carrinho(),
            politica=PoliticaBeneficiosDeliveryV1(
                disponivel=False,
                obrigatoria=True,
            ),
        )


def test_cashback_que_zera_total_remove_obrigacao_financeira() -> None:
    comando, decisao = preparar_checkout_com_beneficios_delivery(
        comando=_comando(),
        contexto_delivery=_contexto_delivery(),
        carrinho=_carrinho(desconto="0.00", cashback="100.00"),
    )

    assert decisao.aceito is True
    assert comando.pedido.total.valor == Decimal("0.00")
    assert comando.pagamento_id is None
    assert comando.metodo_pagamento is None
    assert comando.provedor_pagamento is None


def test_boundary_registra_decisao_e_chama_checkout_canonico(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[ComandoCheckoutV1] = []
    efeitos: list[tuple[tuple[object, ...], tuple[object, ...]]] = []
    sentinel = object()

    def fake_checkout(*, comando: ComandoCheckoutV1, contexto: object, recursos: object) -> object:
        chamadas.append(comando)
        return sentinel

    class RecursosFake:
        def registrar_efeitos(
            self,
            *,
            eventos: tuple[object, ...],
            auditorias: tuple[object, ...],
        ) -> None:
            efeitos.append((eventos, auditorias))

    monkeypatch.setattr(modulo, "executar_checkout_em_transacao", fake_checkout)
    resultado = executar_checkout_delivery_comercial_em_transacao(
        comando=_comando(),
        contexto=_contexto(),
        contexto_delivery=_contexto_delivery(),
        carrinho=_carrinho(),
        recursos=RecursosFake(),  # type: ignore[arg-type]
    )

    assert resultado.checkout is sentinel
    assert resultado.decisao.aceito is True
    assert chamadas[0].pedido.total.valor == Decimal("85.00")
    assert len(efeitos) == 1
    evento, auditoria = efeitos[0][0][0], efeitos[0][1][0]
    assert evento.event_type == "delivery.beneficio.checkout.avaliado.v1"
    assert auditoria.motivo == "beneficio_aplicado"
