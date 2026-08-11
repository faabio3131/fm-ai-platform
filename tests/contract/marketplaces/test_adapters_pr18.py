from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest

from core.marketplaces.erros import ErroMarketplace
from core.marketplaces.food99_partner import (
    FOOD99_CAPACIDADES_PUBLICAS,
    Food99PartnerAdapter,
)
from core.marketplaces.ifood_http import (
    IFOOD_AUTH_URL,
    IFOOD_ORDER_BASE_URL,
    CredencialIfood,
    IfoodHttpAdapter,
    RespostaHttpMarketplace,
)
from core.marketplaces.ifood_sandbox import IFOOD_CAPACIDADES
from core.marketplaces.keeta_partner import (
    KEETA_CAPACIDADES_PUBLICAS,
    KeetaPartnerAdapter,
)
from core.marketplaces.modelos import (
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)


class SegredosFake:
    def __init__(self) -> None:
        self.chamadas = 0

    def obter_ifood(self, segredo_ref: str) -> CredencialIfood:
        assert segredo_ref == "vault://ifood/teste"
        self.chamadas += 1
        return CredencialIfood(client_id="client-id", client_secret="client-secret")


class HttpFake:
    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpMarketplace:
        del timeout_seconds
        self.chamadas.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "form": dict(form or {}),
                "json": dict(json_body or {}),
            }
        )
        if url == IFOOD_AUTH_URL:
            return RespostaHttpMarketplace(
                200, {"accessToken": "token-teste", "expiresIn": 21600}
            )
        if url.endswith("/orders:polling?limit=10"):
            return RespostaHttpMarketplace(
                200,
                {
                    "events": [
                        {
                            "id": "evt-1",
                            "code": "PLC",
                            "fullCode": "PLACED",
                            "orderId": "pedido-1",
                            "merchantId": "merchant-1",
                            "createdAt": "2026-08-11T20:00:00Z",
                        }
                    ]
                },
            )
        if url.endswith("/orders:acknowledgment"):
            return RespostaHttpMarketplace(202, {"status": "ACCEPTED"})
        if url.endswith("/orders/pedido-1") and method == "GET":
            return RespostaHttpMarketplace(
                200,
                {
                    "id": "pedido-1",
                    "status": "CONFIRMED",
                    "createdAt": "2026-08-11T20:00:00Z",
                    "merchant": {"id": "merchant-1", "name": "Loja"},
                    "items": [
                        {
                            "id": "item-cat-1",
                            "uniqueId": "item-pedido-1",
                            "externalCode": "SKU-1",
                            "name": "Burger",
                            "quantity": 2,
                            "unitPrice": 20,
                        }
                    ],
                    "total": {"orderAmount": 40},
                },
            )
        if url.startswith(f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/"):
            return RespostaHttpMarketplace(202, {"status": "ACCEPTED"})
        raise AssertionError(f"chamada HTTP inesperada: {method} {url}")


class TransporteParceiroFake:
    def __init__(self, *, contrato_verificado: bool) -> None:
        self._contrato_verificado = contrato_verificado
        self.acks: list[tuple[str, ...]] = []
        self.comandos: list[str] = []

    @property
    def contrato_verificado(self) -> bool:
        return self._contrato_verificado

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int
    ) -> tuple[EventoMarketplaceExterno, ...]:
        del limite
        return (
            EventoMarketplaceExterno(
                evento_id="evt-partner-1",
                pedido_id_externo="pedido-partner-1",
                merchant_id=integracao.conta_externa,
                codigo="ORDER_CREATED",
                codigo_completo="ORDER_CREATED",
                status=StatusPedidoExterno.RECEBIDO,
                ocorrido_em=datetime.now(timezone.utc),
                payload_hash="a" * 64,
            ),
        )

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None:
        del integracao
        self.acks.append(evento_ids)

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot:
        return PedidoMarketplaceSnapshot(
            id_externo=pedido_id_externo,
            merchant_id=integracao.conta_externa,
            status=StatusPedidoExterno.RECEBIDO,
            total=Decimal(30),
            itens=(
                ItemMarketplace(
                    item_id_externo="i1",
                    sku="sku-1",
                    nome="Item",
                    quantidade=Decimal(1),
                    preco_unitario=Decimal(30),
                ),
            ),
            atualizado_em=datetime.now(timezone.utc),
        )

    def executar_comando(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        comando: str,
        idempotency_key: str,
        status: StatusPedidoExterno | None = None,
        motivo: str | None = None,
    ) -> None:
        del integracao, pedido_id_externo, idempotency_key, status, motivo
        self.comandos.append(comando)


def _integracao(
    plataforma: PlataformaMarketplace,
    *,
    conta: str = "merchant-1",
) -> IntegracaoMarketplace:
    capacidades = {
        PlataformaMarketplace.IFOOD: IFOOD_CAPACIDADES,
        PlataformaMarketplace.FOOD99: FOOD99_CAPACIDADES_PUBLICAS,
        PlataformaMarketplace.KEETA: KEETA_CAPACIDADES_PUBLICAS,
    }[plataforma]
    return IntegracaoMarketplace(
        integracao_id=f"int-{plataforma.value}",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        plataforma=plataforma,
        conta_externa=conta,
        segredo_ref=f"vault://{plataforma.value}/teste",
        capacidades=capacidades,
    )


def test_ifood_http_usa_oauth_polling_ack_e_cache_de_token() -> None:
    http = HttpFake()
    segredos = SegredosFake()
    adapter = IfoodHttpAdapter(http=http, segredos=segredos)
    integracao = _integracao(PlataformaMarketplace.IFOOD)

    eventos = adapter.receber_eventos(integracao, limite=10)
    adapter.reconhecer_eventos(integracao, ("evt-1",))

    assert eventos[0].status is StatusPedidoExterno.RECEBIDO
    assert eventos[0].pedido_id_externo == "pedido-1"
    assert segredos.chamadas == 1
    assert http.chamadas[0]["url"] == IFOOD_AUTH_URL
    assert http.chamadas[0]["form"]["grantType"] == "client_credentials"
    assert http.chamadas[1]["headers"]["Authorization"] == "Bearer token-teste"
    assert http.chamadas[2]["json"] == {"acknowledgedEventIds": ["evt-1"]}


def test_ifood_http_mapeia_snapshot_sem_persistir_pii() -> None:
    adapter = IfoodHttpAdapter(http=HttpFake(), segredos=SegredosFake())
    snapshot = adapter.consultar_pedido(
        _integracao(PlataformaMarketplace.IFOOD), "pedido-1"
    )
    assert snapshot.merchant_id == "merchant-1"
    assert snapshot.status is StatusPedidoExterno.CONFIRMADO
    assert snapshot.total == Decimal("40.00")
    assert snapshot.itens[0].sku == "SKU-1"
    assert snapshot.itens[0].quantidade == Decimal(2)


def test_ifood_http_publica_comandos_oficiais() -> None:
    http = HttpFake()
    adapter = IfoodHttpAdapter(http=http, segredos=SegredosFake())
    integracao = _integracao(PlataformaMarketplace.IFOOD)

    adapter.confirmar(integracao, "pedido-1", idempotency_key="idem-confirm")
    adapter.atualizar_status(
        integracao,
        "pedido-1",
        status=StatusPedidoExterno.EM_PREPARO,
        idempotency_key="idem-preparo",
    )
    adapter.atualizar_status(
        integracao,
        "pedido-1",
        status=StatusPedidoExterno.PRONTO,
        idempotency_key="idem-pronto",
    )
    adapter.atualizar_status(
        integracao,
        "pedido-1",
        status=StatusPedidoExterno.DESPACHADO,
        idempotency_key="idem-despacho",
    )
    adapter.cancelar(
        integracao, "pedido-1", motivo="503", idempotency_key="idem-cancel"
    )

    urls = [chamada["url"] for chamada in http.chamadas]
    assert f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/confirm" in urls
    assert f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/startPreparation" in urls
    assert f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/readyToPickup" in urls
    assert f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/dispatch" in urls
    assert f"{IFOOD_ORDER_BASE_URL}/orders/pedido-1/requestCancellation" in urls
    dispatch = next(c for c in http.chamadas if c["url"].endswith("/dispatch"))
    cancel = next(c for c in http.chamadas if c["url"].endswith("/requestCancellation"))
    assert dispatch["json"] == {"deliveredBy": "MERCHANT"}
    assert cancel["json"] == {"reason": "503"}


@pytest.mark.parametrize(
    ("plataforma", "adapter_cls", "codigo"),
    [
        (PlataformaMarketplace.FOOD99, Food99PartnerAdapter, "contrato_99food_nao_verificado"),
        (PlataformaMarketplace.KEETA, KeetaPartnerAdapter, "contrato_keeta_nao_verificado"),
    ],
)
def test_parceiros_sem_contrato_oficial_falham_fechado(
    plataforma, adapter_cls, codigo: str
) -> None:
    adapter = adapter_cls(TransporteParceiroFake(contrato_verificado=False))
    with pytest.raises(ErroMarketplace, match=codigo):
        adapter.receber_eventos(_integracao(plataforma))


@pytest.mark.parametrize(
    ("plataforma", "adapter_cls"),
    [
        (PlataformaMarketplace.FOOD99, Food99PartnerAdapter),
        (PlataformaMarketplace.KEETA, KeetaPartnerAdapter),
    ],
)
def test_parceiros_com_contrato_verificado_delegam_leitura_sem_inventar_payload(
    plataforma, adapter_cls
) -> None:
    transport = TransporteParceiroFake(contrato_verificado=True)
    adapter = adapter_cls(transport)
    integracao = _integracao(plataforma)
    eventos = adapter.receber_eventos(integracao)
    pedido = adapter.consultar_pedido(integracao, "pedido-partner-1")
    adapter.reconhecer_eventos(integracao, (eventos[0].evento_id,))
    assert pedido.merchant_id == integracao.conta_externa
    assert transport.acks == [("evt-partner-1",)]


@pytest.mark.parametrize(
    ("plataforma", "adapter_cls"),
    [
        (PlataformaMarketplace.FOOD99, Food99PartnerAdapter),
        (PlataformaMarketplace.KEETA, KeetaPartnerAdapter),
    ],
)
def test_mutacoes_nao_documentadas_ficam_bloqueadas(plataforma, adapter_cls) -> None:
    adapter = adapter_cls(TransporteParceiroFake(contrato_verificado=True))
    with pytest.raises(ErroMarketplace, match="capacidade_nao_suportada:confirmar"):
        adapter.confirmar(
            _integracao(plataforma), "pedido-1", idempotency_key="idem"
        )
