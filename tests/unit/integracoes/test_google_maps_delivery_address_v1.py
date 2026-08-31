from core.integracoes.google_maps import (
    ConfiguracaoGoogleMaps,
    GoogleMapsAdapter,
    RespostaHTTPMaps,
)


class HTTPMapsFake:
    def request(self, *, method, url, headers=None, params=None, json_body=None, timeout_seconds):
        del headers, params, json_body, timeout_seconds
        if method == "GET":
            return RespostaHTTPMaps(
                status_code=200,
                payload={
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "Rua A, 10 - Centro, Cidade - SP, 01000-000, Brasil",
                            "place_id": "place-destino",
                            "geometry": {"location": {"lat": -23.5, "lng": -46.6}},
                            "address_components": [
                                {"long_name": "01000-000", "short_name": "01000-000", "types": ["postal_code"]},
                                {"long_name": "Rua A", "short_name": "Rua A", "types": ["route"]},
                                {"long_name": "10", "short_name": "10", "types": ["street_number"]},
                                {"long_name": "Centro", "short_name": "Centro", "types": ["sublocality_level_1"]},
                                {"long_name": "Cidade", "short_name": "Cidade", "types": ["locality"]},
                                {"long_name": "São Paulo", "short_name": "SP", "types": ["administrative_area_level_1"]},
                            ],
                        }
                    ],
                },
            )
        return RespostaHTTPMaps(
            status_code=200,
            payload={
                "routes": [
                    {
                        "distanceMeters": 4200,
                        "duration": "901s",
                        "polyline": {"encodedPolyline": "abc"},
                    }
                ]
            },
        )


def test_geocodificacao_expoe_componentes_necessarios_para_entrega():
    adapter = GoogleMapsAdapter(
        configuracao=ConfiguracaoGoogleMaps(server_api_key="secret"),
        http=HTTPMapsFake(),
    )
    resultado = adapter.geocodificar("Rua A, 10, CEP 01000-000")

    assert resultado.cep == "01000-000"
    assert resultado.logradouro == "Rua A"
    assert resultado.numero == "10"
    assert resultado.bairro == "Centro"
    assert resultado.cidade == "Cidade"
    assert resultado.uf == "SP"
    assert resultado.place_id == "place-destino"
