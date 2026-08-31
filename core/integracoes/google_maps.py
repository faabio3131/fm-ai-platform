"""Adapter Google Maps V1 com contratos injetáveis e falhas fail-closed.

O adapter não lê ambiente, banco ou contexto global. A chave de servidor já
resolvida é injetada na borda e nunca aparece em ``repr`` ou mensagens de erro.
Testes usam transporte/fixtures; o runtime real poderá usar a mesma porta HTTP.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class ErroGoogleMaps(RuntimeError):
    """Falha sanitizada e estável do provedor."""


class ErroGoogleMapsTransitorio(ErroGoogleMaps):
    """Falha elegível para retry controlado."""


@dataclass(frozen=True, kw_only=True)
class RespostaHTTPMaps:
    status_code: int
    payload: Mapping[str, Any] | None


class PortaHTTPMaps(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float,
    ) -> RespostaHTTPMaps: ...


@dataclass(frozen=True, repr=False, kw_only=True)
class ConfiguracaoGoogleMaps:
    server_api_key: str
    language: str = "pt-BR"
    country_code: str = "BR"
    timeout_seconds: float = 8.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.server_api_key.strip():
            raise ValueError("chave servidor Google Maps ausente")
        if not self.language.strip() or not self.country_code.strip():
            raise ValueError("localidade Google Maps incompleta")
        if not 0 < self.timeout_seconds <= 30:
            raise ValueError("timeout Google Maps invalido")
        if not 1 <= self.max_attempts <= 5:
            raise ValueError("tentativas Google Maps invalidas")

    def __repr__(self) -> str:
        return (
            "ConfiguracaoGoogleMaps(server_api_key=***, "
            f"language={self.language!r}, country_code={self.country_code!r}, "
            f"timeout_seconds={self.timeout_seconds!r}, max_attempts={self.max_attempts!r})"
        )


@dataclass(frozen=True, kw_only=True)
class Coordenada:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ErroGoogleMaps("coordenada Google Maps invalida")


@dataclass(frozen=True, kw_only=True)
class ResultadoGeocodificacao:
    endereco_formatado: str
    coordenada: Coordenada
    place_id: str
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    uf: str | None = None


@dataclass(frozen=True, kw_only=True)
class ResultadoRota:
    distancia_metros: int
    duracao_segundos: int
    polyline_codificada: str
    origem: Coordenada
    destino: Coordenada

    @property
    def distancia_km(self) -> float:
        return self.distancia_metros / 1000

    @property
    def eta_minutos(self) -> int:
        return max(1, (self.duracao_segundos + 59) // 60)


class GoogleMapsAdapter:
    GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
    ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
    _RETRYABLE = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        configuracao: ConfiguracaoGoogleMaps,
        http: PortaHTTPMaps,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        self._config = configuracao
        self._http = http
        self._sleep = sleep

    def _request(self, **kwargs: Any) -> Mapping[str, Any]:
        for tentativa in range(1, self._config.max_attempts + 1):
            try:
                resposta = self._http.request(
                    timeout_seconds=self._config.timeout_seconds, **kwargs
                )
            except (TimeoutError, ConnectionError) as exc:
                if tentativa == self._config.max_attempts:
                    raise ErroGoogleMapsTransitorio(
                        "Google Maps indisponivel apos retries"
                    ) from exc
                self._sleep(0.25 * (2 ** (tentativa - 1)))
                continue
            if resposta.status_code in self._RETRYABLE:
                if tentativa == self._config.max_attempts:
                    raise ErroGoogleMapsTransitorio(
                        f"Google Maps respondeu HTTP {resposta.status_code} apos retries"
                    )
                self._sleep(0.25 * (2 ** (tentativa - 1)))
                continue
            if not 200 <= resposta.status_code < 300:
                raise ErroGoogleMaps(
                    f"Google Maps rejeitou requisicao HTTP {resposta.status_code}"
                )
            if not isinstance(resposta.payload, Mapping):
                raise ErroGoogleMaps("Google Maps retornou payload invalido")
            return resposta.payload
        raise AssertionError("retry Google Maps terminou sem resultado")

    @staticmethod
    def _componentes_endereco(primeiro: Mapping[str, Any]) -> dict[str, str]:
        componentes = primeiro.get("address_components")
        if not isinstance(componentes, list):
            return {}

        resultado: dict[str, str] = {}
        for componente in componentes:
            if not isinstance(componente, Mapping):
                continue
            tipos = componente.get("types")
            if not isinstance(tipos, list):
                continue
            long_name = str(componente.get("long_name") or "").strip()
            short_name = str(componente.get("short_name") or "").strip()
            if not long_name:
                continue
            if "postal_code" in tipos:
                resultado["cep"] = long_name
            if "route" in tipos:
                resultado["logradouro"] = long_name
            if "street_number" in tipos:
                resultado["numero"] = long_name
            if "sublocality_level_1" in tipos or "neighborhood" in tipos:
                resultado.setdefault("bairro", long_name)
            if "locality" in tipos or "administrative_area_level_2" in tipos:
                resultado.setdefault("cidade", long_name)
            if "administrative_area_level_1" in tipos:
                resultado["uf"] = short_name or long_name
        return resultado

    def geocodificar(self, endereco: str) -> ResultadoGeocodificacao:
        texto = endereco.strip()
        if not texto:
            raise ErroGoogleMaps("endereco obrigatorio")
        payload = self._request(
            method="GET",
            url=self.GEOCODE_URL,
            params={
                "address": texto,
                "components": f"country:{self._config.country_code}",
                "language": self._config.language,
                "key": self._config.server_api_key,
            },
        )
        if payload.get("status") != "OK":
            status = payload.get("status", "INVALID")
            raise ErroGoogleMaps(f"geocodificacao Google Maps: {status}")
        resultados = payload.get("results")
        try:
            primeiro = resultados[0]  # type: ignore[index]
            if not isinstance(primeiro, Mapping):
                raise TypeError("resultado invalido")
            local = primeiro["geometry"]["location"]
            componentes = self._componentes_endereco(primeiro)
            return ResultadoGeocodificacao(
                endereco_formatado=str(primeiro["formatted_address"]),
                coordenada=Coordenada(
                    latitude=float(local["lat"]), longitude=float(local["lng"])
                ),
                place_id=str(primeiro["place_id"]),
                cep=componentes.get("cep"),
                logradouro=componentes.get("logradouro"),
                numero=componentes.get("numero"),
                bairro=componentes.get("bairro"),
                cidade=componentes.get("cidade"),
                uf=componentes.get("uf"),
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ErroGoogleMaps("resposta de geocodificacao incompleta") from exc

    def calcular_rota(
        self, *, origem: Coordenada, destino: Coordenada
    ) -> ResultadoRota:
        payload = self._request(
            method="POST",
            url=self.ROUTES_URL,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self._config.server_api_key,
                "X-Goog-FieldMask": (
                    "routes.distanceMeters,routes.duration,routes.polyline.encodedPolyline"
                ),
            },
            json_body={
                "origin": {"location": {"latLng": self._lat_lng(origem)}},
                "destination": {"location": {"latLng": self._lat_lng(destino)}},
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_AWARE",
                "languageCode": self._config.language,
                "units": "METRIC",
            },
        )
        try:
            rota = payload["routes"][0]  # type: ignore[index]
            duracao = str(rota["duration"])
            if not duracao.endswith("s"):
                raise ValueError("duration invalida")
            return ResultadoRota(
                distancia_metros=int(rota["distanceMeters"]),
                duracao_segundos=max(0, round(float(duracao[:-1]))),
                polyline_codificada=str(rota["polyline"]["encodedPolyline"]),
                origem=origem,
                destino=destino,
            )
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise ErroGoogleMaps("resposta de rota incompleta") from exc

    @staticmethod
    def _lat_lng(coordenada: Coordenada) -> dict[str, float]:
        return {
            "latitude": coordenada.latitude,
            "longitude": coordenada.longitude,
        }
