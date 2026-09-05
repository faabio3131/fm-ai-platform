from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from core.marketplaces import (
    ConfiguracaoOpenDelivery,
    ErroMarketplace,
    IntegracaoMarketplace,
    OpenDeliveryPartnerTransport,
    PlataformaMarketplace,
    RespostaHttpOpenDelivery,
    RotasOpenDelivery,
    StatusPedidoExterno,
)
from core.marketplaces.food99_partner import FOOD99_CAPACIDADES_PUBLICAS
from core.marketplaces.keeta_partner import (
    KEETA_CAPACIDADES_PUBLICAS,
    KeetaPartnerAdapter,
)


class _AuthFake:
    def cabecalhos(
        self,
        *,
        integracao: IntegracaoMarketplace,
        method: str,
        url: str,
        json_body: Mapping[str, Any] | list[Mapping[str, Any]] | None,
    ) -> Mapping[str, str]:
        del integracao, method, url, json_body
        return {"Authorization": "Bearer fake"}


class _CancelamentoFake:
    def payload_cancelamento(self, *, motivo: str) -> Mapping[str, Any]:
        return {"reason": motivo, "code": "UNAVAILABLE_ITEM", "mode": "MANUAL"}


class _HttpFake:
    def __init__(self, respostas: list[RespostaHttpOpenDelivery]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpOpenDelivery:
        self.chamadas.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json_body": json_body,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.respostas.pop(0)


def _integracao(plataforma: PlataformaMarketplace) -> IntegracaoMarketplace:
    capacidades = (
        FOOD99_CAPACIDADES_PUBLICAS
        if plataforma is PlataformaMarketplace.FOOD99
        else KEETA_CAPACIDADES_PUBLICAS
    )
    return IntegracaoMarketplace(
        integracao_id=f"int-{plataforma.value}",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        plataforma=plataforma,
        conta_externa="merchant-1",
        segredo_ref="secret-ref",
        capacidades=capacidades,
    )


def _config(*, verificado: bool = True) -> ConfiguracaoOpenDelivery:
    return ConfiguracaoOpenDelivery(
        base_url="https://partner.example",
        contrato="Open Delivery Orders",
        versao="1.x",
        contrato_verificado=verificado,
    )


def _pedido() -> Mapping[str, Any]:
    return {
        "id": "order-1",
        "displayId": "A-100",
        "createdAt": "2026-09-05T14:00:00Z",
        "status": "CONFIRMED",
        "merchant": {"id": "merchant-1", "name": "Loja"},
        "items": [
            {
                "id": "item-1",
                "name": "Produto",
                "externalCode": "SKU-1",
                "quantity": 2,
                "unitPrice": {"value": 12.5, "currency": "BRL"},
            }
        ],
        "total": {"orderAmount": {"value": 25, "currency": "BRL"}},
    }


def test_configuracao_exige_https() -> None:
    with pytest.raises(ErroMarketplace) as exc:
        ConfiguracaoOpenDelivery(
            base_url="http://inseguro.example",
            contrato="Open Delivery",
            versao="1.x",
        )

    assert exc.value.codigo == "opendelivery_base_url_invalida"


def test_polling_ack_e_snapshot_sao_normalizados() -> None:
    http = _HttpFake(
        [
            RespostaHttpOpenDelivery(
                status_code=200,
                payload=[
                    {
                        "eventId": "evt-1",
                        "eventType": "CREATED",
                        "orderId": "order-1",
                        "createdAt": "2026-09-05T14:00:00Z",
                    }
                ],
            ),
            RespostaHttpOpenDelivery(status_code=202),
            RespostaHttpOpenDelivery(status_code=200, payload=_pedido()),
        ]
    )
    integracao = _integracao(PlataformaMarketplace.FOOD99)
    transporte = OpenDeliveryPartnerTransport(
        configuracao=_config(),
        autenticacao=_AuthFake(),
        politica_cancelamento=_CancelamentoFake(),
        http=http,
    )

    eventos = transporte.receber_eventos(integracao, limite=10)
    transporte.reconhecer_eventos(integracao, ("evt-1",))
    snapshot = transporte.consultar_pedido(integracao, "order-1")

    assert eventos[0].evento_id == "evt-1"
    assert eventos[0].status is StatusPedidoExterno.RECEBIDO
    assert http.chamadas[1]["json_body"] == [
        {"id": "evt-1", "orderId": "order-1", "eventType": "CREATED"}
    ]
    assert snapshot.status is StatusPedidoExterno.CONFIRMADO
    assert snapshot.total == 25
    assert snapshot.itens[0].sku == "SKU-1"


def test_confirmacao_busca_metadados_e_publica_lifecycle() -> None:
    http = _HttpFake(
        [
            RespostaHttpOpenDelivery(status_code=200, payload=_pedido()),
            RespostaHttpOpenDelivery(status_code=202),
        ]
    )
    integracao = _integracao(PlataformaMarketplace.KEETA)
    transporte = OpenDeliveryPartnerTransport(
        configuracao=_config(),
        autenticacao=_AuthFake(),
        http=http,
    )

    transporte.executar_comando(
        integracao,
        "order-1",
        comando="confirmar",
        idempotency_key="idem-1",
    )

    assert http.chamadas[1]["url"].endswith("/v1/orders/order-1/confirm")
    assert http.chamadas[1]["json_body"] == {
        "createdAt": "2026-09-05T14:00:00Z",
        "orderExternalCode": "A-100",
    }


def test_status_e_cancelamento_respeitam_rotas_e_politica() -> None:
    http = _HttpFake(
        [
            RespostaHttpOpenDelivery(status_code=202),
            RespostaHttpOpenDelivery(status_code=202),
        ]
    )
    integracao = _integracao(PlataformaMarketplace.KEETA)
    transporte = OpenDeliveryPartnerTransport(
        configuracao=ConfiguracaoOpenDelivery(
            base_url="https://open.mykeeta.com/api/open/opendelivery",
            contrato="Keeta Open Delivery",
            versao="1.0.7/Open Delivery 1.5",
            rotas=RotasOpenDelivery(preparando=None),
            contrato_verificado=True,
        ),
        autenticacao=_AuthFake(),
        politica_cancelamento=_CancelamentoFake(),
        http=http,
    )

    transporte.executar_comando(
        integracao,
        "order-1",
        comando="atualizar_status",
        status=StatusPedidoExterno.PRONTO,
        idempotency_key="idem-ready",
    )
    transporte.executar_comando(
        integracao,
        "order-1",
        comando="cancelar",
        motivo="Item indisponível",
        idempotency_key="idem-cancel",
    )

    assert http.chamadas[0]["url"].endswith("/v1/orders/order-1/readyForPickup")
    assert http.chamadas[1]["json_body"] == {
        "reason": "Item indisponível",
        "code": "UNAVAILABLE_ITEM",
        "mode": "MANUAL",
    }


def test_rota_nao_publicada_falha_fechado() -> None:
    transporte = OpenDeliveryPartnerTransport(
        configuracao=ConfiguracaoOpenDelivery(
            base_url="https://open.mykeeta.com/api/open/opendelivery",
            contrato="Keeta Open Delivery",
            versao="1.0.7/Open Delivery 1.5",
            rotas=RotasOpenDelivery(preparando=None),
            contrato_verificado=True,
        ),
        autenticacao=_AuthFake(),
        http=_HttpFake([]),
    )

    with pytest.raises(ErroMarketplace) as exc:
        transporte.executar_comando(
            _integracao(PlataformaMarketplace.KEETA),
            "order-1",
            comando="atualizar_status",
            status=StatusPedidoExterno.EM_PREPARO,
            idempotency_key="idem-preparing",
        )

    assert exc.value.codigo == "opendelivery_comando_nao_suportado"


def test_adapter_keeta_exige_contrato_verificado() -> None:
    transporte = OpenDeliveryPartnerTransport(
        configuracao=_config(verificado=False),
        autenticacao=_AuthFake(),
        http=_HttpFake([]),
    )
    adapter = KeetaPartnerAdapter(transporte)

    with pytest.raises(ErroMarketplace) as exc:
        adapter.receber_eventos(_integracao(PlataformaMarketplace.KEETA))

    assert exc.value.codigo == "contrato_keeta_nao_verificado"
