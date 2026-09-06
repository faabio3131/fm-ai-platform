from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from core.marketplaces import (
    FOOD99_CAPACIDADES_PUBLICAS,
    KEETA_CAPACIDADES_PUBLICAS,
    KEETA_TOKEN_URL,
    CredencialKeeta,
    ErroMarketplace,
    ErroMarketplaceTransitorio,
    IntegracaoMarketplace,
    KeetaAuthOpenDelivery,
    PlataformaMarketplace,
    PoliticaCancelamentoKeeta,
    RespostaHttpOpenDelivery,
    gerar_assinatura_keeta,
)


class _SegredosFake:
    def __init__(self) -> None:
        self.chamadas = 0

    def obter_keeta(self, segredo_ref: str) -> CredencialKeeta:
        assert segredo_ref == "vault://keeta/teste"
        self.chamadas += 1
        return CredencialKeeta(client_id="client-123", client_secret="secret-123")


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
                "headers": dict(headers or {}),
                "json_body": json_body,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.respostas.pop(0)


def _integracao(
    plataforma: PlataformaMarketplace = PlataformaMarketplace.KEETA,
) -> IntegracaoMarketplace:
    capacidades = (
        KEETA_CAPACIDADES_PUBLICAS
        if plataforma is PlataformaMarketplace.KEETA
        else FOOD99_CAPACIDADES_PUBLICAS
    )
    return IntegracaoMarketplace(
        integracao_id=f"int-{plataforma.value}",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        plataforma=plataforma,
        conta_externa="merchant-1",
        segredo_ref="vault://keeta/teste",
        capacidades=capacidades,
    )


def test_credencial_keeta_exige_client_id_e_secret() -> None:
    with pytest.raises(ErroMarketplace) as exc:
        CredencialKeeta(client_id="", client_secret="secret")

    assert exc.value.codigo == "credencial_keeta_invalida"


def test_assinatura_keeta_canonicaliza_body_e_usa_hmac_sha256_base64() -> None:
    assinatura = gerar_assinatura_keeta(
        url=(
            "https://open.mykeeta.com/api/open/opendelivery/"
            "v1/orders/order-1/confirm"
        ),
        json_body={
            "orderExternalCode": "A-100",
            "createdAt": "2026-09-05T14:00:00Z",
        },
        client_secret="secret-123",
    )

    assert assinatura == "ecsIObIcXNNkfvlQgogA/g2CG82nDCRjeGBpfgiycxM="


def test_assinatura_keeta_ordena_query_params() -> None:
    assinatura = gerar_assinatura_keeta(
        url="https://example.com/path?z=2&a=1",
        json_body=None,
        client_secret="secret",
    )

    assert assinatura == "BhfpI+v10rddk6FYr3TQw+prGn67doUErDWsAoohgDA="


def test_auth_keeta_obtem_app_level_token_assina_e_reutiliza_cache() -> None:
    http = _HttpFake(
        [
            RespostaHttpOpenDelivery(
                status_code=200,
                payload={
                    "access_token": "token-keeta",
                    "token_type": "bearer",
                    "expires_in": 3600,
                },
            )
        ]
    )
    segredos = _SegredosFake()
    auth = KeetaAuthOpenDelivery(http=http, segredos=segredos)
    integracao = _integracao()
    url = "https://open.mykeeta.com/api/open/opendelivery/v1/events:polling"

    headers_1 = auth.cabecalhos(
        integracao=integracao,
        method="GET",
        url=url,
        json_body=None,
    )
    headers_2 = auth.cabecalhos(
        integracao=integracao,
        method="GET",
        url=url,
        json_body=None,
    )

    assert headers_1["Authorization"] == "Bearer token-keeta"
    assert headers_1["X-App-Signature"]
    assert headers_2 == headers_1
    assert segredos.chamadas == 1
    assert len(http.chamadas) == 1
    assert http.chamadas[0]["url"] == KEETA_TOKEN_URL
    assert http.chamadas[0]["json_body"] == {
        "client_id": "client-123",
        "grant_type": "app_level_token",
        "client_secret": "secret-123",
    }


def test_auth_keeta_normaliza_indisponibilidade_transitoria() -> None:
    auth = KeetaAuthOpenDelivery(
        http=_HttpFake([RespostaHttpOpenDelivery(status_code=503)]),
        segredos=_SegredosFake(),
    )

    with pytest.raises(ErroMarketplaceTransitorio) as exc:
        auth.cabecalhos(
            integracao=_integracao(),
            method="GET",
            url="https://open.mykeeta.com/api/open/opendelivery/v1/events:polling",
            json_body=None,
        )

    assert exc.value.codigo == "keeta_auth_indisponivel"


def test_auth_keeta_rejeita_integracao_de_outra_plataforma() -> None:
    auth = KeetaAuthOpenDelivery(
        http=_HttpFake([]),
        segredos=_SegredosFake(),
    )

    with pytest.raises(ErroMarketplace) as exc:
        auth.cabecalhos(
            integracao=_integracao(PlataformaMarketplace.FOOD99),
            method="GET",
            url="https://open.mykeeta.com/api/open/opendelivery/v1/events:polling",
            json_body=None,
        )

    assert exc.value.codigo == "integracao_plataforma_incompativel"


def test_politica_cancelamento_keeta_exige_codigo_oficial() -> None:
    politica = PoliticaCancelamentoKeeta(codigo="unavailable_item", modo="manual")

    assert politica.payload_cancelamento(motivo="Item sem estoque") == {
        "reason": "Item sem estoque",
        "code": "UNAVAILABLE_ITEM",
        "mode": "MANUAL",
    }

    with pytest.raises(ErroMarketplace) as exc:
        PoliticaCancelamentoKeeta(codigo="CODIGO_INVENTADO")

    assert exc.value.codigo == "keeta_codigo_cancelamento_invalido"
