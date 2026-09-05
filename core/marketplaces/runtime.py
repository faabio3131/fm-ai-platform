"""Composição de adapters reais de marketplace para runtime comercial.

A camada mantém o domínio e os adapters independentes de biblioteca HTTP e de
provedor de segredos. Nenhuma credencial é lida ou persistida aqui: produção
deve injetar uma implementação de ``PortaSegredosIfood``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from .adapters import RegistroAdaptersMarketplace
from .erros import ErroMarketplace, ErroMarketplaceTransitorio
from .flags import ifood_adapter_v1_enabled
from .ifood_http import (
    IfoodHttpAdapter,
    PortaHttpMarketplace,
    PortaSegredosIfood,
    RespostaHttpMarketplace,
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
                if isinstance(bruto, Mapping):
                    payload = bruto
                elif isinstance(bruto, list) and all(
                    isinstance(item, Mapping) for item in bruto
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


def compor_adapters_marketplace_reais(
    *,
    segredos_ifood: PortaSegredosIfood | None = None,
    http_ifood: PortaHttpMarketplace | None = None,
    registro: RegistroAdaptersMarketplace | None = None,
) -> RegistroAdaptersMarketplace:
    """Registra apenas adapters reais explicitamente habilitados.

    99Food e Keeta não são compostos aqui enquanto seus transportes parceiros
    não possuírem contrato oficial verificado. Isso evita promover fakes ou
    inferências de endpoint para o runtime comercial.
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
    return adapters
