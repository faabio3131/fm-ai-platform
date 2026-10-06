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

from core.ai_router import ConteudoAudioIA
from core.integracoes.google_maps import RespostaHTTPMaps
from core.integracoes.provedores import (
    ErroProvedorExterno,
    RespostaBinariaProvedor,
    RespostaProvedor,
)


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


class RequestsBinaryTransport:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    def get(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> RespostaBinariaProvedor:
        try:
            resposta = self._session.get(
                url,
                headers=dict(headers),
                timeout=timeout_seconds,
            )
        except requests.Timeout as exc:
            raise TimeoutError("timeout no download de midia externa") from exc
        except requests.RequestException as exc:
            raise ConnectionError("falha de transporte no download de midia externa") from exc
        return RespostaBinariaProvedor(
            status_code=resposta.status_code,
            content=bytes(resposta.content),
            content_type=resposta.headers.get("content-type"),
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
                    retry_options=types.HttpRetryOptions(attempts=4),
                ),
            )
            provider_contents = contents
            if isinstance(contents, ConteudoAudioIA):
                provider_contents = [
                    contents.instrucao,
                    types.Part.from_bytes(
                        data=contents.audio,
                        mime_type=contents.mime_type,
                    ),
                ]
            return client.models.generate_content(
                model=model,
                contents=provider_contents,
            )
        except TimeoutError:
            raise
        except Exception as exc:
            texto = str(exc).casefold()
            if "timeout" in texto or "temporar" in texto:
                raise TimeoutError("Gemini temporariamente indisponivel") from exc
            raise ConnectionError("falha segura no gateway Gemini") from exc


class OpenAIChatTenantGateway:
    """Chat Completions OpenAI textual, sem SDK e sem cache cruzado entre tenants."""

    BASE_URL = "https://api.openai.com/v1/chat/completions"
    _RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()

    @staticmethod
    def _messages(contents: Any) -> list[dict[str, str]]:
        if isinstance(contents, ConteudoAudioIA):
            raise ErroProvedorExterno("OpenAI Luna nao aceita audio nesta rota")

        if isinstance(contents, Mapping):
            system = str(contents.get("system") or "").strip()
            user = str(contents.get("user") or "").strip()
            tools = str(contents.get("tools") or "").strip()
            if tools:
                system = "\n".join(
                    part for part in (
                        system,
                        f"Catalogo de tools V1 permitido: {tools}",
                    ) if part
                )
            messages: list[dict[str, str]] = []
            if system:
                messages.append({"role": "system", "content": system})
            if user:
                messages.append({"role": "user", "content": user})
            if not messages:
                messages.append({"role": "user", "content": str(dict(contents))})
            return messages

        return [{"role": "user", "content": str(contents)}]

    def create_chat_completion(
        self,
        *,
        api_key: str,
        model: str,
        contents: Any,
        timeout_seconds: float,
    ) -> Any:
        if not api_key.strip() or not model.strip():
            raise ErroProvedorExterno("OpenAI configuracao incompleta")

        resposta = _request(
            self._session,
            method="POST",
            url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            params=None,
            json_body={
                "model": model,
                "reasoning_effort": "low",
                "messages": self._messages(contents),
            },
            timeout_seconds=timeout_seconds,
        )

        if resposta.status_code in self._RETRYABLE:
            raise ConnectionError(
                f"OpenAI indisponivel HTTP {resposta.status_code}"
            )
        if not 200 <= resposta.status_code < 300:
            raise ErroProvedorExterno(
                f"OpenAI rejeitou requisicao HTTP {resposta.status_code}"
            )

        payload = _payload_json(resposta)
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ErroProvedorExterno("OpenAI retornou payload invalido")
        first = choices[0]
        if not isinstance(first, Mapping):
            raise ErroProvedorExterno("OpenAI retornou payload invalido")
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise ErroProvedorExterno("OpenAI retornou payload invalido")
        text_value = message.get("content")
        if not isinstance(text_value, str) or not text_value.strip():
            raise ErroProvedorExterno("OpenAI retornou conteudo invalido")

        usage = payload.get("usage")
        prompt_tokens = None
        completion_tokens = None
        cached_tokens = None
        if isinstance(usage, Mapping):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            details = usage.get("prompt_tokens_details")
            if isinstance(details, Mapping):
                cached_tokens = details.get("cached_tokens")

        return {
            "text": text_value.strip(),
            "usage_metadata": {
                "prompt_token_count": prompt_tokens,
                "candidates_token_count": completion_tokens,
                "cached_content_token_count": cached_tokens,
            },
        }
