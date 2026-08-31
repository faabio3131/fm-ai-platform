from __future__ import annotations

from types import SimpleNamespace

from core.ai_router import ConteudoAudioIA
from infra.integracoes import transportes
from infra.integracoes.transportes import GoogleGenAITenantGateway


class _FakeModels:
    def __init__(self, captured: dict) -> None:
        self._captured = captured

    def generate_content(self, *, model, contents):
        self._captured["model"] = model
        self._captured["contents"] = contents
        return {"text": "transcricao"}


class _FakeClient:
    def __init__(self, captured: dict, **kwargs) -> None:
        captured["client_kwargs"] = kwargs
        self.models = _FakeModels(captured)


def test_gateway_traduz_audio_neutro_somente_no_boundary(monkeypatch) -> None:
    captured: dict = {}

    fake_types = SimpleNamespace(
        HttpOptions=lambda **kwargs: ("http", kwargs),
        HttpRetryOptions=lambda **kwargs: ("retry", kwargs),
        Part=SimpleNamespace(
            from_bytes=lambda **kwargs: ("part-from-bytes", kwargs),
        ),
    )

    monkeypatch.setattr(transportes, "types", fake_types)
    monkeypatch.setattr(
        transportes.genai,
        "Client",
        lambda **kwargs: _FakeClient(captured, **kwargs),
    )

    gateway = GoogleGenAITenantGateway()
    resposta = gateway.generate_content(
        api_key="chave-secreta",
        model="gemini-test",
        contents=ConteudoAudioIA(
            audio=b"bytes-de-audio",
            mime_type="audio/ogg",
            instrucao="Transcreva fielmente.",
        ),
        timeout_seconds=5.0,
    )

    assert resposta == {"text": "transcricao"}
    assert captured["model"] == "gemini-test"
    assert captured["contents"][0] == "Transcreva fielmente."
    assert captured["contents"][1] == (
        "part-from-bytes",
        {"data": b"bytes-de-audio", "mime_type": "audio/ogg"},
    )
    assert "bytes-de-audio" not in repr(captured["client_kwargs"])
