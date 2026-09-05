from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from core.marketplaces import (
    CredencialIfood,
    CredencialKeeta,
    ErroMarketplace,
    ErroMarketplaceTransitorio,
    HttpxMarketplaceTransport,
    PlataformaMarketplace,
    RegistroAdaptersMarketplace,
    RespostaHttpMarketplace,
    RespostaHttpOpenDelivery,
    compor_adapters_marketplace_reais,
    compor_ifood_http_real,
    compor_keeta_opendelivery_real,
)


class _SegredosFake:
    def obter_ifood(self, segredo_ref: str) -> CredencialIfood:
        assert segredo_ref
        return CredencialIfood(client_id="client", client_secret="secret")


class _SegredosKeetaFake:
    def obter_keeta(self, segredo_ref: str) -> CredencialKeeta:
        assert segredo_ref
        return CredencialKeeta(client_id="client-keeta", client_secret="secret-keeta")


class _HttpFake:
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
        del method, url, headers, form, json_body, timeout_seconds
        return RespostaHttpMarketplace(status_code=200, payload={})


class _HttpKeetaFake:
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | list[Mapping[str, Any]] | None = None,
        timeout_seconds: float = 10.0,
    ) -> RespostaHttpOpenDelivery:
        del method, url, headers, json_body, timeout_seconds
        return RespostaHttpOpenDelivery(status_code=200, payload={})


class _RespostaFake:
    status_code = 200
    content = b'{"ok": true}'

    @staticmethod
    def json() -> Mapping[str, Any]:
        return {"ok": True}


class _ClientFake:
    def __init__(self) -> None:
        self.chamadas: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> _RespostaFake:
        self.chamadas.append(kwargs)
        return _RespostaFake()


def _env_ifood_real() -> dict[str, str]:
    return {
        "FM_AI_MARKETPLACE_V1": "1",
        "FM_AI_IFOOD_ADAPTER_V1": "1",
        "FM_AI_ADAPTER_ORDERS": "real",
        "FM_AI_ADAPTER_AUTH": "real",
        "FM_AI_ADAPTER_IFOOD": "http",
    }


def _env_keeta_real() -> dict[str, str]:
    return {
        "FM_AI_MARKETPLACE_V1": "1",
        "FM_AI_KEETA_ADAPTER_V1": "1",
        "FM_AI_ADAPTER_ORDERS": "real",
        "FM_AI_ADAPTER_AUTH": "real",
        "FM_AI_ADAPTER_KEETA": "http",
    }


def test_httpx_marketplace_transport_normaliza_json_sem_rede_real() -> None:
    client = _ClientFake()
    transporte = HttpxMarketplaceTransport(client=client)  # type: ignore[arg-type]

    resposta = transporte.request(
        method="POST",
        url="https://example.invalid/test",
        headers={"X-Test": "1"},
        form={"a": "b"},
        timeout_seconds=7.5,
    )

    assert resposta.status_code == 200
    assert resposta.payload == {"ok": True}
    assert client.chamadas[0]["timeout"] == 7.5
    assert client.chamadas[0]["data"] == {"a": "b"}


def test_httpx_marketplace_transport_normaliza_falha_de_rede() -> None:
    class _ClientFalhando:
        def request(self, **kwargs: Any) -> None:
            del kwargs
            request = httpx.Request("GET", "https://example.invalid")
            raise httpx.ConnectError("offline", request=request)

    transporte = HttpxMarketplaceTransport(client=_ClientFalhando())  # type: ignore[arg-type]

    with pytest.raises(ErroMarketplaceTransitorio) as exc:
        transporte.request(method="GET", url="https://example.invalid")

    assert exc.value.codigo == "marketplace_http_indisponivel"


def test_ifood_real_falha_fechado_quando_readiness_nao_libera() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(ErroMarketplace) as exc:
        compor_ifood_http_real(segredos=_SegredosFake(), http=_HttpFake())

    assert exc.value.codigo == "ifood_adapter_real_nao_habilitado"


def test_registro_ifood_real_exige_provedor_de_segredos() -> None:
    with (
        patch.dict(os.environ, _env_ifood_real(), clear=True),
        pytest.raises(ErroMarketplace) as exc,
    ):
        compor_adapters_marketplace_reais(http_ifood=_HttpFake())

    assert exc.value.codigo == "ifood_segredos_nao_configurados"


def test_registro_ifood_real_composto_quando_readiness_esta_verde() -> None:
    registro = RegistroAdaptersMarketplace()
    with patch.dict(os.environ, _env_ifood_real(), clear=True):
        resultado = compor_adapters_marketplace_reais(
            segredos_ifood=_SegredosFake(),
            http_ifood=_HttpFake(),
            registro=registro,
        )

    assert resultado is registro
    assert registro.obter(PlataformaMarketplace.IFOOD).plataforma is PlataformaMarketplace.IFOOD


def test_keeta_real_falha_fechado_quando_readiness_nao_libera() -> None:
    with patch.dict(os.environ, {}, clear=True), pytest.raises(ErroMarketplace) as exc:
        compor_keeta_opendelivery_real(
            segredos=_SegredosKeetaFake(),
            http=_HttpKeetaFake(),
        )

    assert exc.value.codigo == "keeta_adapter_real_nao_habilitado"


def test_registro_keeta_real_exige_provedor_de_segredos() -> None:
    with (
        patch.dict(os.environ, _env_keeta_real(), clear=True),
        pytest.raises(ErroMarketplace) as exc,
    ):
        compor_adapters_marketplace_reais(http_keeta=_HttpKeetaFake())

    assert exc.value.codigo == "keeta_segredos_nao_configurados"


def test_registro_keeta_real_composto_quando_readiness_esta_verde() -> None:
    registro = RegistroAdaptersMarketplace()
    with patch.dict(os.environ, _env_keeta_real(), clear=True):
        resultado = compor_adapters_marketplace_reais(
            segredos_keeta=_SegredosKeetaFake(),
            http_keeta=_HttpKeetaFake(),
            registro=registro,
        )

    assert resultado is registro
    assert registro.obter(PlataformaMarketplace.KEETA).plataforma is PlataformaMarketplace.KEETA
