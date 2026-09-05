"""Transporte normalizado Open Delivery para parceiros de marketplace.

O protocolo de pedidos fica separado de autenticação, assinatura e política de
cancelamento específicas de cada parceiro. Assim, 99Food/Keeta podem reutilizar
o mesmo contrato anticorrupção sem compartilhar credenciais ou particularidades.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx

from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .modelos import (
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    StatusPedidoExterno,
    hash_payload,
)

JsonObject = Mapping[str, Any]
JsonArray = list[Mapping[str, Any]]
JsonBody = JsonObject | JsonArray


@dataclass(frozen=True)
class RespostaHttpOpenDelivery:
    status_code: int
    payload: JsonObject | JsonArray | None = None


class PortaHttpOpenDelivery(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        json_body: JsonBody | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpOpenDelivery: ...


class PortaAutenticacaoOpenDelivery(Protocol):
    def cabecalhos(
        self,
        *,
        integracao: IntegracaoMarketplace,
        method: str,
        url: str,
        json_body: JsonBody | None,
    ) -> Mapping[str, str]: ...


class PortaPoliticaCancelamentoOpenDelivery(Protocol):
    def payload_cancelamento(self, *, motivo: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class RotasOpenDelivery:
    polling: str = "/v1/events:polling"
    acknowledgment: str = "/v1/events/acknowledgment"
    pedido: str = "/v1/orders/{order_id}"
    confirmar: str = "/v1/orders/{order_id}/confirm"
    preparando: str | None = "/v1/orders/{order_id}/preparing"
    pronto: str = "/v1/orders/{order_id}/readyForPickup"
    despachar: str | None = "/v1/orders/{order_id}/dispatch"
    entregar: str | None = "/v1/orders/{order_id}/delivered"
    cancelar: str = "/v1/orders/{order_id}/requestCancellation"


@dataclass(frozen=True)
class ConfiguracaoOpenDelivery:
    base_url: str
    contrato: str
    versao: str
    rotas: RotasOpenDelivery = RotasOpenDelivery()
    contrato_verificado: bool = False

    def __post_init__(self) -> None:
        base = self.base_url.strip().rstrip("/")
        if not base.startswith("https://"):
            raise ErroMarketplace("opendelivery_base_url_invalida")
        if not self.contrato.strip() or not self.versao.strip():
            raise ErroMarketplace("opendelivery_contrato_invalido")
        object.__setattr__(self, "base_url", base)


class HttpxOpenDeliveryTransport:
    """Porta HTTP real, sem conhecer token, segredo ou assinatura do parceiro."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client()

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        json_body: JsonBody | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpOpenDelivery:
        if timeout_seconds <= 0:
            raise ErroMarketplace("opendelivery_http_timeout_invalido")
        try:
            resposta = self._client.request(
                method=method,
                url=url,
                headers=dict(headers) if headers is not None else None,
                json=json_body,
                timeout=timeout_seconds,
            )
        except httpx.TransportError as exc:
            raise ErroMarketplaceTransitorio("opendelivery_http_indisponivel") from exc

        payload: JsonObject | JsonArray | None = None
        if resposta.content:
            try:
                bruto = resposta.json()
            except ValueError as exc:
                if resposta.status_code < 400:
                    raise ErroMarketplace("opendelivery_http_payload_invalido") from exc
            else:
                if isinstance(bruto, Mapping):
                    payload = bruto
                elif isinstance(bruto, list) and all(
                    isinstance(item, Mapping) for item in bruto
                ):
                    payload = bruto
                elif resposta.status_code < 400:
                    raise ErroMarketplace("opendelivery_http_payload_invalido")

        return RespostaHttpOpenDelivery(
            status_code=resposta.status_code,
            payload=payload,
        )


_STATUS: dict[str, StatusPedidoExterno] = {
    "CREATED": StatusPedidoExterno.RECEBIDO,
    "PLACED": StatusPedidoExterno.RECEBIDO,
    "PENDING": StatusPedidoExterno.RECEBIDO,
    "CONFIRMED": StatusPedidoExterno.CONFIRMADO,
    "PREPARING": StatusPedidoExterno.EM_PREPARO,
    "READY": StatusPedidoExterno.PRONTO,
    "READY_FOR_PICKUP": StatusPedidoExterno.PRONTO,
    "DISPATCHED": StatusPedidoExterno.DESPACHADO,
    "IN_DELIVERY": StatusPedidoExterno.DESPACHADO,
    "PICKED_UP": StatusPedidoExterno.DESPACHADO,
    "DELIVERED": StatusPedidoExterno.CONCLUIDO,
    "CONCLUDED": StatusPedidoExterno.CONCLUIDO,
    "DONE": StatusPedidoExterno.CONCLUIDO,
    "CANCELLED": StatusPedidoExterno.CANCELADO,
    "CANCELED": StatusPedidoExterno.CANCELADO,
}


def _status(valor: object) -> StatusPedidoExterno:
    return _STATUS.get(str(valor or "").upper(), StatusPedidoExterno.DESCONHECIDO)


def _timestamp(valor: object) -> datetime:
    texto = str(valor or "").strip()
    if not texto:
        raise ErroMarketplace("opendelivery_timestamp_ausente")
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ErroMarketplace("opendelivery_timestamp_invalido") from exc


def _valor_monetario(valor: object) -> Decimal:
    if isinstance(valor, Mapping):
        valor = valor.get("value", "0")
    return Decimal(str(valor or "0"))


class OpenDeliveryPartnerTransport:
    """Implementa o contrato parceiro normalizado sobre Open Delivery Orders."""

    def __init__(
        self,
        *,
        configuracao: ConfiguracaoOpenDelivery,
        autenticacao: PortaAutenticacaoOpenDelivery,
        politica_cancelamento: PortaPoliticaCancelamentoOpenDelivery | None = None,
        http: PortaHttpOpenDelivery | None = None,
    ) -> None:
        self.configuracao = configuracao
        self.autenticacao = autenticacao
        self.politica_cancelamento = politica_cancelamento
        self.http = http or HttpxOpenDeliveryTransport()
        self._ack_cache: dict[str, dict[str, str]] = {}

    @property
    def contrato_verificado(self) -> bool:
        return self.configuracao.contrato_verificado

    def _url(self, rota: str, *, pedido_id: str | None = None) -> str:
        if pedido_id is not None:
            rota = rota.format(order_id=pedido_id)
        return f"{self.configuracao.base_url}{rota}"

    def _request(
        self,
        integracao: IntegracaoMarketplace,
        *,
        method: str,
        rota: str,
        pedido_id: str | None = None,
        json_body: JsonBody | None = None,
    ) -> RespostaHttpOpenDelivery:
        url = self._url(rota, pedido_id=pedido_id)
        headers = dict(
            self.autenticacao.cabecalhos(
                integracao=integracao,
                method=method,
                url=url,
                json_body=json_body,
            )
        )
        if json_body is not None:
            headers.setdefault("Content-Type", "application/json")
        resposta = self.http.request(
            method=method,
            url=url,
            headers=headers,
            json_body=json_body,
        )
        if resposta.status_code == 429 or resposta.status_code >= 500:
            raise ErroMarketplaceTransitorio(
                f"opendelivery_http_{resposta.status_code}"
            )
        if resposta.status_code >= 400:
            raise ErroMarketplace(f"opendelivery_http_{resposta.status_code}")
        return resposta

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int
    ) -> tuple[EventoMarketplaceExterno, ...]:
        if limite < 1 or limite > 100:
            raise ErroMarketplace("limite_polling_invalido")
        resposta = self._request(
            integracao,
            method="GET",
            rota=self.configuracao.rotas.polling,
        )
        if resposta.status_code == 204 or resposta.payload is None:
            return ()
        if not isinstance(resposta.payload, list):
            raise ErroMarketplace("opendelivery_eventos_invalidos")

        eventos: list[EventoMarketplaceExterno] = []
        for bruto in resposta.payload[:limite]:
            evento_id = str(bruto.get("eventId") or bruto.get("id") or "").strip()
            pedido_id = str(bruto.get("orderId") or "").strip()
            evento_tipo = str(
                bruto.get("eventType") or bruto.get("fullCode") or bruto.get("code") or ""
            ).strip()
            criado = _timestamp(bruto.get("createdAt"))
            if not evento_id or not pedido_id or not evento_tipo:
                raise ErroMarketplace("opendelivery_evento_invalido")
            merchant_id = str(bruto.get("merchantId") or integracao.conta_externa).strip()
            self._ack_cache[evento_id] = {
                "id": evento_id,
                "orderId": pedido_id,
                "eventType": evento_tipo,
            }
            eventos.append(
                EventoMarketplaceExterno(
                    evento_id=evento_id,
                    pedido_id_externo=pedido_id,
                    merchant_id=merchant_id,
                    codigo=evento_tipo,
                    codigo_completo=evento_tipo,
                    status=_status(evento_tipo),
                    ocorrido_em=criado,
                    payload_hash=hash_payload(bruto),
                    versao_externa=(
                        str(bruto["version"]) if bruto.get("version") is not None else None
                    ),
                )
            )
        return tuple(eventos)

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None:
        if not evento_ids:
            return
        desconhecidos = [evento_id for evento_id in evento_ids if evento_id not in self._ack_cache]
        if desconhecidos:
            raise ErroMarketplace("opendelivery_ack_evento_nao_cacheado")
        body: JsonArray = [self._ack_cache[evento_id] for evento_id in evento_ids]
        resposta = self._request(
            integracao,
            method="POST",
            rota=self.configuracao.rotas.acknowledgment,
            json_body=body,
        )
        if resposta.status_code not in {200, 202, 204}:
            raise ErroMarketplace("opendelivery_ack_rejeitado")
        for evento_id in evento_ids:
            self._ack_cache.pop(evento_id, None)

    def _pedido_bruto(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> Mapping[str, Any]:
        resposta = self._request(
            integracao,
            method="GET",
            rota=self.configuracao.rotas.pedido,
            pedido_id=pedido_id_externo,
        )
        if not isinstance(resposta.payload, Mapping):
            raise ErroMarketplace("opendelivery_pedido_invalido")
        return resposta.payload

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot:
        bruto = self._pedido_bruto(integracao, pedido_id_externo)
        merchant = bruto.get("merchant")
        itens_brutos = bruto.get("items")
        total = bruto.get("total")
        if not isinstance(itens_brutos, list) or not isinstance(total, Mapping):
            raise ErroMarketplace("opendelivery_pedido_invalido")
        merchant_id = integracao.conta_externa
        if isinstance(merchant, Mapping) and merchant.get("id"):
            merchant_id = str(merchant["id"])
        if merchant_id != integracao.conta_externa:
            raise ErroMarketplace("pedido_de_outra_conta")

        itens: list[ItemMarketplace] = []
        for item in itens_brutos:
            if not isinstance(item, Mapping):
                raise ErroMarketplace("opendelivery_item_invalido")
            unit_price = item.get("unitPrice")
            itens.append(
                ItemMarketplace(
                    item_id_externo=str(item.get("id") or ""),
                    sku=(str(item["externalCode"]) if item.get("externalCode") else None),
                    nome=str(item.get("name") or ""),
                    quantidade=Decimal(str(item.get("quantity") or "0")),
                    preco_unitario=_valor_monetario(unit_price),
                )
            )

        order_amount = total.get("orderAmount")
        atualizado = bruto.get("updatedAt") or bruto.get("createdAt")
        status_bruto = bruto.get("status") or bruto.get("lastEvent")
        return PedidoMarketplaceSnapshot(
            id_externo=str(bruto.get("id") or pedido_id_externo),
            merchant_id=merchant_id,
            status=_status(status_bruto),
            total=_valor_monetario(order_amount),
            itens=tuple(itens),
            atualizado_em=_timestamp(atualizado),
            versao_externa=(
                str(bruto["version"]) if bruto.get("version") is not None else None
            ),
        )

    def _executar_sem_body(
        self,
        integracao: IntegracaoMarketplace,
        *,
        pedido_id_externo: str,
        rota: str | None,
    ) -> None:
        if rota is None:
            raise ErroMarketplace("opendelivery_comando_nao_suportado")
        resposta = self._request(
            integracao,
            method="POST",
            rota=rota,
            pedido_id=pedido_id_externo,
        )
        if resposta.status_code not in {200, 202, 204}:
            raise ErroMarketplace("opendelivery_comando_rejeitado")

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
        del idempotency_key
        rotas = self.configuracao.rotas
        if comando == "confirmar":
            bruto = self._pedido_bruto(integracao, pedido_id_externo)
            criado = str(bruto.get("createdAt") or "").strip()
            externo = str(bruto.get("orderExternalCode") or bruto.get("displayId") or "").strip()
            if not criado or not externo:
                raise ErroMarketplace("opendelivery_confirmacao_sem_metadados")
            resposta = self._request(
                integracao,
                method="POST",
                rota=rotas.confirmar,
                pedido_id=pedido_id_externo,
                json_body={"createdAt": criado, "orderExternalCode": externo},
            )
            if resposta.status_code not in {200, 202, 204}:
                raise ErroMarketplace("opendelivery_confirmacao_rejeitada")
            return

        if comando in {"rejeitar", "cancelar"}:
            if self.politica_cancelamento is None:
                raise ErroMarketplace("opendelivery_politica_cancelamento_ausente")
            motivo_normalizado = str(motivo or "").strip()
            if not motivo_normalizado:
                raise ErroMarketplace("motivo_cancelamento_obrigatorio")
            body = self.politica_cancelamento.payload_cancelamento(
                motivo=motivo_normalizado
            )
            resposta = self._request(
                integracao,
                method="POST",
                rota=rotas.cancelar,
                pedido_id=pedido_id_externo,
                json_body=body,
            )
            if resposta.status_code not in {200, 202, 204}:
                raise ErroMarketplace("opendelivery_cancelamento_rejeitado")
            return

        if comando != "atualizar_status" or status is None:
            raise ErroMarketplace("opendelivery_comando_invalido")
        rota_status = {
            StatusPedidoExterno.EM_PREPARO: rotas.preparando,
            StatusPedidoExterno.PRONTO: rotas.pronto,
            StatusPedidoExterno.DESPACHADO: rotas.despachar,
            StatusPedidoExterno.CONCLUIDO: rotas.entregar,
        }.get(status)
        self._executar_sem_body(
            integracao,
            pedido_id_externo=pedido_id_externo,
            rota=rota_status,
        )
