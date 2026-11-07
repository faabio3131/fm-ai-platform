"""Composição de adapters reais de marketplace para runtime comercial.

A camada mantém o domínio e os adapters independentes de biblioteca HTTP e de
provedor de segredos. Nenhuma credencial é persistida aqui: produção deve
injetar as portas de segredos específicas de cada parceiro habilitado.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .adapters import RegistroAdaptersMarketplace
from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .flags import (
    food99_adapter_v1_enabled,
    ifood_adapter_v1_enabled,
    keeta_adapter_v1_enabled,
)
from .food99_partner import Food99PartnerAdapter
from .ifood_http import (
    IfoodHttpAdapter,
    PortaHttpMarketplace,
    PortaSegredosIfood,
    RespostaHttpMarketplace,
)
from .keeta_auth import (
    KEETA_CONTRATO,
    KEETA_OPEN_DELIVERY_BASE_URL,
    KEETA_VERSAO,
    KeetaAuthOpenDelivery,
    PortaSegredosKeeta,
)
from .keeta_partner import KeetaPartnerAdapter
from .partner_transport import TransporteParceiroNormalizado
from .opendelivery import (
    ConfiguracaoOpenDelivery,
    HttpxOpenDeliveryTransport,
    OpenDeliveryPartnerTransport,
    PortaHttpOpenDelivery,
    PortaPoliticaCancelamentoOpenDelivery,
    RotasOpenDelivery,
)


class HttpxMarketplaceTransport:
    """Transporte HTTP real com timeout e normalização de falhas de rede."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client()

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
        if timeout_seconds <= 0:
            raise ErroMarketplace("marketplace_http_timeout_invalido")
        try:
            resposta = self._client.request(
                method=method,
                url=url,
                headers=dict(headers) if headers is not None else None,
                data=dict(form) if form is not None else None,
                json=dict(json_body) if json_body is not None else None,
                timeout=timeout_seconds,
            )
        except httpx.TransportError as exc:
            raise ErroMarketplaceTransitorio("marketplace_http_indisponivel") from exc

        payload: Mapping[str, Any] | list[Mapping[str, Any]] | None = None
        if resposta.content:
            try:
                bruto = resposta.json()
            except ValueError as exc:
                if resposta.status_code < 400:
                    raise ErroMarketplace("marketplace_http_payload_invalido") from exc
            else:
                if isinstance(bruto, Mapping) or (
                    isinstance(bruto, list)
                    and all(isinstance(item, Mapping) for item in bruto)
                ):
                    payload = bruto
                elif resposta.status_code < 400:
                    raise ErroMarketplace("marketplace_http_payload_invalido")

        return RespostaHttpMarketplace(
            status_code=resposta.status_code,
            payload=payload,
        )


def compor_ifood_http_real(
    *,
    segredos: PortaSegredosIfood,
    http: PortaHttpMarketplace | None = None,
) -> IfoodHttpAdapter:
    """Compõe iFood real somente quando o readiness comercial o libera."""

    if not ifood_adapter_v1_enabled():
        raise ErroMarketplace("ifood_adapter_real_nao_habilitado")
    return IfoodHttpAdapter(
        http=http or HttpxMarketplaceTransport(),
        segredos=segredos,
    )


def compor_keeta_opendelivery_real(
    *,
    segredos: PortaSegredosKeeta,
    http: PortaHttpOpenDelivery | None = None,
    politica_cancelamento: PortaPoliticaCancelamentoOpenDelivery | None = None,
) -> KeetaPartnerAdapter:
    """Compõe Keeta real usando somente contrato oficial Open Delivery publicado."""

    if not keeta_adapter_v1_enabled():
        raise ErroMarketplace("keeta_adapter_real_nao_habilitado")
    transporte_http = http or HttpxOpenDeliveryTransport()
    autenticacao = KeetaAuthOpenDelivery(http=transporte_http, segredos=segredos)
    transporte = OpenDeliveryPartnerTransport(
        configuracao=ConfiguracaoOpenDelivery(
            base_url=KEETA_OPEN_DELIVERY_BASE_URL,
            contrato=KEETA_CONTRATO,
            versao=KEETA_VERSAO,
            rotas=RotasOpenDelivery(preparando=None),
            contrato_verificado=True,
        ),
        autenticacao=autenticacao,
        politica_cancelamento=politica_cancelamento,
        http=transporte_http,
    )
    return KeetaPartnerAdapter(transporte)


def compor_food99_transporte_verificado(
    *, transporte: TransporteParceiroNormalizado,
) -> Food99PartnerAdapter:
    """Aceita transporte certificado pelo parceiro, não inventa autenticação."""
    if not food99_adapter_v1_enabled():
        raise ErroMarketplace("99food_adapter_real_nao_habilitado")
    if not transporte.contrato_verificado:
        raise ErroMarketplace("contrato_99food_nao_verificado")
    return Food99PartnerAdapter(transporte)


def compor_adapters_marketplace_reais(
    *,
    segredos_ifood: PortaSegredosIfood | None = None,
    http_ifood: PortaHttpMarketplace | None = None,
    segredos_keeta: PortaSegredosKeeta | None = None,
    http_keeta: PortaHttpOpenDelivery | None = None,
    politica_cancelamento_keeta: PortaPoliticaCancelamentoOpenDelivery | None = None,
    transporte_food99: TransporteParceiroNormalizado | None = None,
    registro: RegistroAdaptersMarketplace | None = None,
) -> RegistroAdaptersMarketplace:
    """Registra somente adapters habilitados e com contrato provado.

    iFood/Keeta possuem composição HTTP específica. 99Food exige transporte
    injetado após verificação oficial de autenticação, rotas e payloads.
    """

    adapters = registro or RegistroAdaptersMarketplace()
    if ifood_adapter_v1_enabled():
        if segredos_ifood is None:
            raise ErroMarketplace("ifood_segredos_nao_configurados")
        adapters.registrar(
            IfoodHttpAdapter(
                http=http_ifood or HttpxMarketplaceTransport(),
                segredos=segredos_ifood,
            )
        )

    if keeta_adapter_v1_enabled():
        if segredos_keeta is None:
            raise ErroMarketplace("keeta_segredos_nao_configurados")
        adapters.registrar(
            compor_keeta_opendelivery_real(
                segredos=segredos_keeta,
                http=http_keeta,
                politica_cancelamento=politica_cancelamento_keeta,
            )
        )
    if food99_adapter_v1_enabled():
        if transporte_food99 is None:
            raise ErroMarketplace("99food_transporte_certificado_ausente")
        adapters.registrar(
            compor_food99_transporte_verificado(
                transporte=transporte_food99,
            )
        )
    return adapters
