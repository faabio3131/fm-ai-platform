"""Adapter iFood sobre contrato HTTP oficial, sem rede real nesta PR.

O transporte HTTP e o resolvedor de segredos são portas injetáveis. Testes usam
fakes; nenhuma credencial ou chamada externa é executada pela PR18.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Protocol

from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .ifood_sandbox import IFOOD_CAPACIDADES
from .modelos import (
    CapacidadeMarketplace,
    CapacidadesMarketplace,
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    ItemMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
    hash_payload,
)

IFOOD_AUTH_URL = "https://merchant-api.ifood.com.br/authentication/v1.0/oauth/token"
IFOOD_ORDER_BASE_URL = "https://merchant-api.ifood.com.br/order/v1.0"

_STATUS_EVENTO: dict[str, StatusPedidoExterno] = {
    "PLC": StatusPedidoExterno.RECEBIDO,
    "PLACED": StatusPedidoExterno.RECEBIDO,
    "CFM": StatusPedidoExterno.CONFIRMADO,
    "CONFIRMED": StatusPedidoExterno.CONFIRMADO,
    "RTP": StatusPedidoExterno.PRONTO,
    "READY_TO_PICKUP": StatusPedidoExterno.PRONTO,
    "DSP": StatusPedidoExterno.DESPACHADO,
    "DISPATCHED": StatusPedidoExterno.DESPACHADO,
    "CON": StatusPedidoExterno.CONCLUIDO,
    "CONCLUDED": StatusPedidoExterno.CONCLUIDO,
    "CAN": StatusPedidoExterno.CANCELADO,
    "CANCELLED": StatusPedidoExterno.CANCELADO,
}

_STATUS_PEDIDO: dict[str, StatusPedidoExterno] = {
    "PLACED": StatusPedidoExterno.RECEBIDO,
    "CONFIRMED": StatusPedidoExterno.CONFIRMADO,
    "READY_TO_PICKUP": StatusPedidoExterno.PRONTO,
    "DISPATCHED": StatusPedidoExterno.DESPACHADO,
    "CONCLUDED": StatusPedidoExterno.CONCLUIDO,
    "CANCELLED": StatusPedidoExterno.CANCELADO,
}


@dataclass(frozen=True)
class CredencialIfood:
    client_id: str
    client_secret: str

    def __post_init__(self) -> None:
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ErroMarketplace("credencial_ifood_invalida")


@dataclass(frozen=True)
class RespostaHttpMarketplace:
    status_code: int
    payload: Mapping[str, Any] | list[Mapping[str, Any]] | None = None


class PortaSegredosIfood(Protocol):
    def obter_ifood(self, segredo_ref: str) -> CredencialIfood: ...


class PortaHttpMarketplace(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        form: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpMarketplace: ...


class IfoodHttpAdapter:
    def __init__(self, *, http: PortaHttpMarketplace, segredos: PortaSegredosIfood) -> None:
        self.http = http
        self.segredos = segredos
        self._tokens: dict[str, tuple[str, datetime]] = {}

    @property
    def plataforma(self) -> PlataformaMarketplace:
        return PlataformaMarketplace.IFOOD

    @property
    def capacidades(self) -> CapacidadesMarketplace:
        return IFOOD_CAPACIDADES

    @staticmethod
    def _validar_integracao(integracao: IntegracaoMarketplace) -> None:
        if integracao.plataforma is not PlataformaMarketplace.IFOOD:
            raise ErroMarketplace("integracao_plataforma_incompativel")

    def _token(self, integracao: IntegracaoMarketplace) -> str:
        self._validar_integracao(integracao)
        agora = datetime.now(timezone.utc)
        cache = self._tokens.get(integracao.segredo_ref)
        if cache is not None and cache[1] > agora + timedelta(minutes=1):
            return cache[0]
        credencial = self.segredos.obter_ifood(integracao.segredo_ref)
        resposta = self.http.request(
            method="POST",
            url=IFOOD_AUTH_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            form={
                "grantType": "client_credentials",
                "clientId": credencial.client_id,
                "clientSecret": credencial.client_secret,
            },
        )
        if resposta.status_code >= 500:
            raise ErroMarketplaceTransitorio("ifood_auth_indisponivel")
        if resposta.status_code != 200 or not isinstance(resposta.payload, Mapping):
            raise ErroMarketplace("ifood_auth_rejeitada")
        token = str(resposta.payload.get("accessToken", "")).strip()
        expira = int(resposta.payload.get("expiresIn", 21600))
        if not token:
            raise ErroMarketplace("ifood_token_ausente")
        self._tokens[integracao.segredo_ref] = (token, agora + timedelta(seconds=expira))
        return token

    def _request(
        self,
        integracao: IntegracaoMarketplace,
        *,
        method: str,
        path: str,
        json_body: Mapping[str, Any] | None = None,
    ) -> RespostaHttpMarketplace:
        token = self._token(integracao)
        resposta = self.http.request(
            method=method,
            url=f"{IFOOD_ORDER_BASE_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json_body=json_body,
        )
        if resposta.status_code in {429, 500, 502, 503, 504}:
            raise ErroMarketplaceTransitorio(f"ifood_http_{resposta.status_code}")
        if resposta.status_code >= 400:
            raise ErroMarketplace(f"ifood_http_{resposta.status_code}")
        return resposta

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int = 100
    ) -> tuple[EventoMarketplaceExterno, ...]:
        if limite < 1 or limite > 100:
            raise ErroMarketplace("limite_polling_invalido")
        resposta = self._request(
            integracao, method="GET", path=f"/orders:polling?limit={limite}"
        )
        payload = resposta.payload
        if isinstance(payload, Mapping):
            bruto_eventos = payload.get("events", [])
        elif isinstance(payload, list):
            bruto_eventos = payload
        else:
            bruto_eventos = []
        if not isinstance(bruto_eventos, list):
            raise ErroMarketplace("ifood_eventos_invalidos")
        eventos: list[EventoMarketplaceExterno] = []
        for bruto in bruto_eventos:
            if not isinstance(bruto, Mapping):
                raise ErroMarketplace("ifood_evento_invalido")
            codigo = str(bruto.get("code", ""))
            completo = str(bruto.get("fullCode", codigo))
            criado = datetime.fromisoformat(
                str(bruto.get("createdAt", "")).replace("Z", "+00:00")
            )
            eventos.append(
                EventoMarketplaceExterno(
                    evento_id=str(bruto.get("id", "")),
                    pedido_id_externo=str(bruto.get("orderId", "")),
                    merchant_id=str(bruto.get("merchantId", "")),
                    codigo=codigo,
                    codigo_completo=completo,
                    status=_STATUS_EVENTO.get(
                        codigo,
                        _STATUS_EVENTO.get(completo, StatusPedidoExterno.DESCONHECIDO),
                    ),
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
        resposta = self._request(
            integracao,
            method="POST",
            path="/orders:acknowledgment",
            json_body={"acknowledgedEventIds": list(evento_ids)},
        )
        if resposta.status_code not in {200, 202, 204}:
            raise ErroMarketplace("ifood_ack_rejeitado")

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot:
        resposta = self._request(
            integracao, method="GET", path=f"/orders/{pedido_id_externo}"
        )
        if not isinstance(resposta.payload, Mapping):
            raise ErroMarketplace("pedido_ifood_invalido")
        bruto = resposta.payload
        merchant = bruto.get("merchant")
        total = bruto.get("total")
        itens_brutos = bruto.get("items")
        if not isinstance(merchant, Mapping) or not isinstance(total, Mapping):
            raise ErroMarketplace("pedido_ifood_invalido")
        if not isinstance(itens_brutos, list):
            raise ErroMarketplace("pedido_ifood_sem_itens")
        merchant_id = str(merchant.get("id", ""))
        if merchant_id != integracao.conta_externa:
            raise ErroMarketplace("pedido_de_outra_conta")
        itens: list[ItemMarketplace] = []
        for item in itens_brutos:
            if not isinstance(item, Mapping):
                raise ErroMarketplace("item_ifood_invalido")
            itens.append(
                ItemMarketplace(
                    item_id_externo=str(item.get("uniqueId") or item.get("id") or ""),
                    sku=(str(item["externalCode"]) if item.get("externalCode") else None),
                    nome=str(item.get("name", "")),
                    quantidade=Decimal(str(item.get("quantity", "0"))),
                    preco_unitario=Decimal(str(item.get("unitPrice", "0"))),
                )
            )
        status_bruto = str(bruto.get("status", "")).upper()
        atualizado = bruto.get("updatedAt") or bruto.get("createdAt")
        if not atualizado:
            raise ErroMarketplace("pedido_ifood_sem_timestamp")
        return PedidoMarketplaceSnapshot(
            id_externo=str(bruto.get("id", pedido_id_externo)),
            merchant_id=merchant_id,
            status=_STATUS_PEDIDO.get(status_bruto, StatusPedidoExterno.DESCONHECIDO),
            total=Decimal(str(total.get("orderAmount", "0"))),
            itens=tuple(itens),
            atualizado_em=datetime.fromisoformat(str(atualizado).replace("Z", "+00:00")),
            versao_externa=(str(bruto["version"]) if bruto.get("version") else None),
        )

    def _comando(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> None:
        resposta = self._request(
            integracao,
            method="POST",
            path=f"/orders/{pedido_id_externo}/{path}",
            json_body=body,
        )
        if resposta.status_code not in {200, 202, 204}:
            raise ErroMarketplace("ifood_comando_rejeitado")

    def confirmar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        idempotency_key: str,
    ) -> None:
        del idempotency_key
        self._comando(integracao, pedido_id_externo, path="confirm")

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del integracao, pedido_id_externo, motivo, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.REJEITAR)

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> None:
        del idempotency_key
        path = {
            StatusPedidoExterno.EM_PREPARO: "startPreparation",
            StatusPedidoExterno.PRONTO: "readyToPickup",
            StatusPedidoExterno.DESPACHADO: "dispatch",
        }.get(status)
        if path is None:
            raise ErroMarketplace("status_ifood_nao_publicavel")
        body = {"deliveredBy": "MERCHANT"} if status is StatusPedidoExterno.DESPACHADO else None
        self._comando(integracao, pedido_id_externo, path=path, body=body)

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del idempotency_key
        codigo = motivo.strip()
        if not codigo:
            raise ErroMarketplace("motivo_cancelamento_obrigatorio")
        self._comando(
            integracao,
            pedido_id_externo,
            path="requestCancellation",
            body={"reason": codigo},
        )
