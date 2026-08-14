"""Transportes reais para os contratos externos da V1.

Somente status e JSON estruturado atravessam a borda. Corpos de erro, headers de
autorização e credenciais nunca são copiados para exceções da aplicação.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests
from google import genai
from google.genai import types

from core.integracoes.google_maps import RespostaHTTPMaps
from core.integracoes.provedores import RespostaProvedor


def _payload_json(resposta: requests.Response) -> Mapping[str, Any]:
    try:
        payload = resposta.json()
    except (requests.JSONDecodeError, ValueError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _request(
    session: requests.Session,
    *,
    method: str,
    url: str,
    headers: Mapping[str, str] | None,
    params: Mapping[str, str] | None,
    json_body: Mapping[str, Any] | None,
    timeout_seconds: float,
) -> requests.Response:
    try:
        return session.request(
            method,
            url,
            headers=dict(headers or {}),
            params=dict(params or {}),
            json=dict(json_body) if json_body is not None else None,
            timeout=timeout_seconds,
        )
    except requests.Timeout as exc:
        raise TimeoutError("timeout do provedor externo") from exc
    except requests.RequestException as exc:
        raise ConnectionError("falha de transporte do provedor externo") from exc


class RequestsGoogleMapsTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
        timeout_seconds: float,
    ) -> RespostaHTTPMaps:
        resposta = _request(
            self._session,
            method=method,
            url=url,
            headers=headers,
            params=params,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )
        return RespostaHTTPMaps(
            status_code=resposta.status_code,
            payload=_payload_json(resposta),
        )


class RequestsProviderTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> RespostaProvedor:
        resposta = _request(
            self._session,
            method=method,
            url=url,
            headers=headers,
            params=None,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )
        return RespostaProvedor(
            status_code=resposta.status_code,
            payload=_payload_json(resposta),
        )


class GoogleGenAITenantGateway:
    """Cliente Gemini efêmero por chamada, sem cache cruzado entre tenants."""

    def generate_content(
        self,
        *,
        api_key: str,
        model: str,
        contents: Any,
        timeout_seconds: float,
    ) -> Any:
        try:
            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=round(timeout_seconds * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            return client.models.generate_content(model=model, contents=contents)
        except TimeoutError:
            raise
        except Exception as exc:
            texto = str(exc).casefold()
            if "timeout" in texto or "temporar" in texto:
                raise TimeoutError("Gemini temporariamente indisponivel") from exc
            raise ConnectionError("falha segura no gateway Gemini") from exc
