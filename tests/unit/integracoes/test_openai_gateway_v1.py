from __future__ import annotations

from typing import Any

import pytest

from core.ai_router import ConteudoAudioIA
from core.integracoes.provedores import ErroProvedorExterno
from infra.integracoes.transportes import OpenAIChatTenantGateway


class FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self.response


def test_openai_gateway_monta_chat_governado_e_normaliza_usage() -> None:
    session = FakeSession(
        FakeResponse(
            status_code=200,
            payload={
                "choices": [
                    {
                        "message": {
                            "content": '{"tool":"consultar_pedidos","argumentos":{}}'
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                    "prompt_tokens_details": {"cached_tokens": 20},
                },
            },
        )
    )
    gateway = OpenAIChatTenantGateway(session=session)  # type: ignore[arg-type]

    result = gateway.create_chat_completion(
        api_key="sk-test-secret",
        model="gpt-5.6-luna",
        contents={
            "system": "Responda apenas JSON.",
            "user": "Consulte os pedidos.",
            "tools": "consultar_pedidos, consultar_atrasos",
        },
        timeout_seconds=8.0,
    )

    call = session.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-test-secret"
    assert call["json"]["model"] == "gpt-5.6-luna"
    assert call["json"]["reasoning_effort"] == "low"
    assert call["json"]["messages"][0]["role"] == "system"
    assert "consultar_pedidos" in call["json"]["messages"][0]["content"]
    assert call["json"]["messages"][1] == {
        "role": "user",
        "content": "Consulte os pedidos.",
    }
    assert result["text"].startswith('{"tool"')
    assert result["usage_metadata"] == {
        "prompt_token_count": 120,
        "candidates_token_count": 30,
        "cached_content_token_count": 20,
    }


def test_openai_gateway_rejeita_audio_na_rota_luna() -> None:
    session = FakeSession(FakeResponse(status_code=200, payload={}))
    gateway = OpenAIChatTenantGateway(session=session)  # type: ignore[arg-type]

    with pytest.raises(ErroProvedorExterno, match="nao aceita audio"):
        gateway.create_chat_completion(
            api_key="sk-test-secret",
            model="gpt-5.6-luna",
            contents=ConteudoAudioIA(
                audio=b"audio",
                mime_type="audio/ogg",
                instrucao="Transcreva.",
            ),
            timeout_seconds=8.0,
        )

    assert session.calls == []


def test_openai_gateway_sanitiza_erro_http_sem_expor_chave_ou_corpo() -> None:
    session = FakeSession(
        FakeResponse(
            status_code=401,
            payload={"error": {"message": "segredo-do-provedor"}},
        )
    )
    gateway = OpenAIChatTenantGateway(session=session)  # type: ignore[arg-type]

    with pytest.raises(ErroProvedorExterno) as captured:
        gateway.create_chat_completion(
            api_key="sk-test-secret",
            model="gpt-5.6-luna",
            contents="teste",
            timeout_seconds=8.0,
        )

    message = str(captured.value)
    assert "401" in message
    assert "sk-test-secret" not in message
    assert "segredo-do-provedor" not in message
