"""Autenticação e assinatura oficiais da Keeta Open Delivery.

A implementação mantém client_id/client_secret atrás de uma porta de segredos,
obtém token pelo endpoint OAuth oficial e assina cada chamada Open Delivery com
HMAC-SHA256/Base64 no header ``X-App-Signature``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .modelos import IntegracaoMarketplace, PlataformaMarketplace
from .opendelivery import JsonBody, PortaHttpOpenDelivery

KEETA_OPEN_DELIVERY_BASE_URL = "https://open.mykeeta.com/api/open/opendelivery"
KEETA_TOKEN_URL = f"{KEETA_OPEN_DELIVERY_BASE_URL}/oauth/token"
KEETA_CONTRATO = "Keeta Open Delivery"
KEETA_VERSAO = "Open Delivery 1.5.0"

KEETA_CODIGOS_CANCELAMENTO = frozenset(
    {
        "SYSTEMIC_ISSUES",
        "DUPLICATE_APPLICATION",
        "UNAVAILABLE_ITEM",
        "RESTAURANT_WITHOUT_DELIVERY_PERSON",
        "OUTDATED_MENU",
        "ORDER_OUTSIDE_THE_DELIVERY_AREA",
        "BLOCKED_CUSTOMER",
        "OUTSIDE_DELIVERY_HOURS",
        "INTERNAL_DIFFICULTIES_OF_THE_RESTAURANT",
        "RISK_AREA",
        "DELIVERY_PROBLEM",
    }
)
KEETA_MODOS_CANCELAMENTO = frozenset({"AUTO", "MANUAL"})


@dataclass(frozen=True)
class CredencialKeeta:
    client_id: str
    client_secret: str

    def __post_init__(self) -> None:
        if not self.client_id.strip() or not self.client_secret.strip():
            raise ErroMarketplace("credencial_keeta_invalida")


class PortaSegredosKeeta(Protocol):
    def obter_keeta(self, segredo_ref: str) -> CredencialKeeta: ...


def _json_assinavel(json_body: JsonBody | None) -> str:
    if json_body is None:
        return ""
    if isinstance(json_body, Mapping) and not json_body:
        return ""
    try:
        return json.dumps(
            json_body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ErroMarketplace("keeta_payload_assinatura_invalido") from exc


def gerar_assinatura_keeta(
    *,
    url: str,
    json_body: JsonBody | None,
    client_secret: str,
) -> str:
    """Gera a assinatura HMAC-SHA256/Base64 conforme o contrato Keeta."""

    segredo = client_secret.strip()
    partes_url = urlsplit(url)
    if partes_url.scheme != "https" or not partes_url.netloc or not segredo:
        raise ErroMarketplace("keeta_assinatura_configuracao_invalida")

    base_url = urlunsplit(
        (partes_url.scheme, partes_url.netloc, partes_url.path, "", "")
    )
    componentes = [base_url]
    for chave, valor in sorted(parse_qsl(partes_url.query, keep_blank_values=True)):
        componentes.append(f"{chave}={valor}")

    body = _json_assinavel(json_body)
    if body:
        componentes.append(body)

    mensagem = "&".join(componentes).encode("utf-8")
    assinatura = hmac.new(segredo.encode("utf-8"), mensagem, hashlib.sha256).digest()
    return base64.b64encode(assinatura).decode("utf-8")


class KeetaAuthOpenDelivery:
    """Porta de autenticação Open Delivery com token e assinatura Keeta."""

    def __init__(
        self,
        *,
        http: PortaHttpOpenDelivery,
        segredos: PortaSegredosKeeta,
    ) -> None:
        self.http = http
        self.segredos = segredos
        self._tokens: dict[str, tuple[str, datetime, CredencialKeeta]] = {}

    @staticmethod
    def _validar_integracao(integracao: IntegracaoMarketplace) -> None:
        if integracao.plataforma is not PlataformaMarketplace.KEETA:
            raise ErroMarketplace("integracao_plataforma_incompativel")

    def _token_e_credencial(
        self, integracao: IntegracaoMarketplace
    ) -> tuple[str, CredencialKeeta]:
        self._validar_integracao(integracao)
        agora = datetime.now(timezone.utc)
        cache = self._tokens.get(integracao.segredo_ref)
        if cache is not None and cache[1] > agora + timedelta(minutes=1):
            return cache[0], cache[2]

        credencial = self.segredos.obter_keeta(integracao.segredo_ref)
        resposta = self.http.request(
            method="POST",
            url=KEETA_TOKEN_URL,
            headers={"Content-Type": "application/json"},
            json_body={
                "client_id": credencial.client_id,
                "grant_type": "app_level_token",
                "client_secret": credencial.client_secret,
            },
        )
        if resposta.status_code == 429 or resposta.status_code >= 500:
            raise ErroMarketplaceTransitorio("keeta_auth_indisponivel")
        if resposta.status_code != 200 or not isinstance(resposta.payload, Mapping):
            raise ErroMarketplace("keeta_auth_rejeitada")

        token = str(resposta.payload.get("access_token") or "").strip()
        try:
            expira = int(resposta.payload.get("expires_in") or 0)
        except (TypeError, ValueError) as exc:
            raise ErroMarketplace("keeta_token_expiracao_invalida") from exc
        if not token:
            raise ErroMarketplace("keeta_token_ausente")
        if expira <= 0:
            raise ErroMarketplace("keeta_token_expiracao_invalida")

        self._tokens[integracao.segredo_ref] = (
            token,
            agora + timedelta(seconds=expira),
            credencial,
        )
        return token, credencial

    def cabecalhos(
        self,
        *,
        integracao: IntegracaoMarketplace,
        method: str,
        url: str,
        json_body: JsonBody | None,
    ) -> Mapping[str, str]:
        del method
        token, credencial = self._token_e_credencial(integracao)
        return {
            "Authorization": f"Bearer {token}",
            "X-App-Signature": gerar_assinatura_keeta(
                url=url,
                json_body=json_body,
                client_secret=credencial.client_secret,
            ),
        }


@dataclass(frozen=True)
class PoliticaCancelamentoKeeta:
    """Política explícita: nenhum código de cancelamento é inferido do texto."""

    codigo: str
    modo: str = "MANUAL"

    def __post_init__(self) -> None:
        codigo = self.codigo.strip().upper()
        modo = self.modo.strip().upper()
        if codigo not in KEETA_CODIGOS_CANCELAMENTO:
            raise ErroMarketplace("keeta_codigo_cancelamento_invalido")
        if modo not in KEETA_MODOS_CANCELAMENTO:
            raise ErroMarketplace("keeta_modo_cancelamento_invalido")
        object.__setattr__(self, "codigo", codigo)
        object.__setattr__(self, "modo", modo)

    def payload_cancelamento(self, *, motivo: str) -> Mapping[str, Any]:
        razao = motivo.strip()
        if not razao:
            raise ErroMarketplace("motivo_cancelamento_obrigatorio")
        return {"reason": razao, "code": self.codigo, "mode": self.modo}
