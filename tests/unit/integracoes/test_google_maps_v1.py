from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from core.integracoes.google_maps import (
    ConfiguracaoGoogleMaps,
    Coordenada,
    ErroGoogleMaps,
    ErroGoogleMapsTransitorio,
    GoogleMapsAdapter,
    RespostaHTTPMaps,
)


class HTTPFixture:
    def __init__(self, respostas: list[RespostaHTTPMaps | Exception]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> RespostaHTTPMaps:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _adapter(http: HTTPFixture, sleeps: list[float] | None = None) -> GoogleMapsAdapter:
    return GoogleMapsAdapter(
        configuracao=ConfiguracaoGoogleMaps(server_api_key="server-secret"),
        http=http,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def test_geocodificacao_usa_chave_servidor_e_normaliza_fixture() -> None:
    http = HTTPFixture(
        [
            RespostaHTTPMaps(
                status_code=200,
                payload={
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "Av. Paulista, Sao Paulo - SP",
                            "place_id": "place-1",
                            "geometry": {"location": {"lat": -23.56, "lng": -46.65}},
                        }
                    ],
                },
            )
        ]
    )

    resultado = _adapter(http).geocodificar("Av. Paulista")

    assert resultado.place_id == "place-1"
    assert resultado.coordenada == Coordenada(latitude=-23.56, longitude=-46.65)
    assert http.chamadas[0]["timeout_seconds"] == 8.0
    assert http.chamadas[0]["params"]["key"] == "server-secret"


def test_rota_distancia_e_eta_sao_derivadas_da_resposta_oficial() -> None:
    http = HTTPFixture(
        [
            RespostaHTTPMaps(
                status_code=200,
                payload={
                    "routes": [
                        {
                            "distanceMeters": 7250,
                            "duration": "901s",
                            "polyline": {"encodedPolyline": "abc123"},
                        }
                    ]
                },
            )
        ]
    )
    origem = Coordenada(latitude=-23.56, longitude=-46.65)
    destino = Coordenada(latitude=-23.50, longitude=-46.61)

    rota = _adapter(http).calcular_rota(origem=origem, destino=destino)

    assert rota.distancia_km == 7.25
    assert rota.eta_minutos == 16
    assert rota.polyline_codificada == "abc123"
    assert http.chamadas[0]["headers"]["X-Goog-Api-Key"] == "server-secret"


def test_timeout_e_429_aplicam_backoff_limitado_sem_expor_segredo() -> None:
    sleeps: list[float] = []
    http = HTTPFixture(
        [
            TimeoutError("server-secret"),
            RespostaHTTPMaps(status_code=429, payload={"error": "server-secret"}),
            RespostaHTTPMaps(status_code=503, payload=None),
        ]
    )

    with pytest.raises(ErroGoogleMapsTransitorio) as capturado:
        _adapter(http, sleeps).geocodificar("Rua A")

    assert sleeps == [0.25, 0.5]
    assert len(http.chamadas) == 3
    assert "server-secret" not in str(capturado.value)
    assert "server-secret" not in repr(
        ConfiguracaoGoogleMaps(server_api_key="server-secret")
    )


@pytest.mark.parametrize(
    "payload",
    (
        {"status": "ZERO_RESULTS", "results": []},
        {"status": "OK", "results": [{}]},
    ),
)
def test_geocodificacao_falha_fechada_com_payload_incompleto(
    payload: Mapping[str, Any],
) -> None:
    http = HTTPFixture([RespostaHTTPMaps(status_code=200, payload=payload)])
    with pytest.raises(ErroGoogleMaps):
        _adapter(http).geocodificar("Rua inexistente")
