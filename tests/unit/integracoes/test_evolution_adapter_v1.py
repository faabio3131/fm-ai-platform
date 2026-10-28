from __future__ import annotations

import base64
import json

import pytest

from core.integracoes.evolution import (
    ConfiguracaoEvolution,
    EvolutionAdapter,
    nome_instancia_evolution,
)
from core.integracoes.provedores import ErroProvedorExterno, RespostaProvedor


class HTTPFake:
    def __init__(self, responses: list[RespostaProvedor]) -> None:
        self.responses = responses
        self.calls: list[dict] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def _adapter(http: HTTPFake) -> EvolutionAdapter:
    return EvolutionAdapter(
        configuracao=ConfiguracaoEvolution(
            base_url="https://evolution.internal.example",
            api_key="platform-secret",
            webhook_token="w" * 32,
            instance_name=nome_instancia_evolution("tenant-a", "unit-a"),
        ),
        http=http,
    )


def test_nome_da_instancia_e_deterministico_e_isolado_por_unidade() -> None:
    first = nome_instancia_evolution("tenant-a", "unit-a")
    assert first == nome_instancia_evolution("tenant-a", "unit-a")
    assert first != nome_instancia_evolution("tenant-a", "unit-b")
    assert first.startswith("kord-") and len(first) == 37


def test_qr_code_valida_png_e_nao_persiste_segredo() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"safe-image"
    http = HTTPFake(
        [
            RespostaProvedor(
                status_code=200,
                payload={"base64": base64.b64encode(png).decode()},
            )
        ]
    )
    qr = _adapter(http).obter_qr_code()
    assert qr.startswith("data:image/png;base64,")
    assert http.calls[0]["headers"]["apikey"] == "platform-secret"


def test_webhook_exige_token_e_instancia_e_ignora_mensagem_propria() -> None:
    adapter = _adapter(HTTPFake([]))
    instance = adapter.instance_name
    body = json.dumps(
        {
            "instance": instance,
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "msg-1",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Olá"},
                "messageTimestamp": 123,
            },
        }
    ).encode()
    with pytest.raises(ErroProvedorExterno, match="autenticacao"):
        adapter.extrair_mensagens_whatsapp(payload_bruto=body, assinatura="errado")
    messages = adapter.extrair_mensagens_whatsapp(
        payload_bruto=body, assinatura="w" * 32
    )
    assert len(messages) == 1
    assert messages[0].mensagem_id == "evo:msg-1"
    assert messages[0].remetente == "5511999999999"
    assert messages[0].texto == "Olá"


def test_envio_consulta_sessao_antes_de_postar_e_nao_faz_fallback() -> None:
    instance = nome_instancia_evolution("tenant-a", "unit-a")
    http = HTTPFake(
        [
            RespostaProvedor(
                status_code=200,
                payload={"instance": {"instanceName": instance, "state": "open"}},
            ),
            RespostaProvedor(status_code=200, payload={"key": {"id": "out-1"}}),
        ]
    )
    result = _adapter(http).enviar_whatsapp(
        destinatario="+55 (11) 99999-9999",
        texto="Resposta",
        idempotency_key="reply-1",
    )
    assert result == "out-1"
    assert [call["method"] for call in http.calls] == ["GET", "POST"]
    assert http.calls[1]["url"].endswith(f"/message/sendText/{instance}")
    assert http.calls[1]["json_body"] == {
        "number": "5511999999999",
        "text": "Resposta",
    }


def test_audio_recebido_usa_referencia_assinada_e_download_limitado() -> None:
    audio = b"ogg-audio-seguro"
    http = HTTPFake(
        [
            RespostaProvedor(
                status_code=200,
                payload={
                    "base64": base64.b64encode(audio).decode(),
                    "mimetype": "audio/ogg; codecs=opus",
                },
            )
        ]
    )
    adapter = _adapter(http)
    body = json.dumps(
        {
            "instance": adapter.instance_name,
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "audio-1",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"audioMessage": {"mimetype": "audio/ogg; codecs=opus"}},
                "messageTimestamp": 456,
            },
        }
    ).encode()
    messages = adapter.extrair_mensagens_whatsapp(
        payload_bruto=body, assinatura="w" * 32
    )
    assert len(messages) == 1
    assert messages[0].tipo == "audio"
    assert messages[0].media_id is not None
    result, mime_type = adapter.baixar_audio_whatsapp(
        media_id=messages[0].media_id,
        mime_type_declarado=messages[0].mime_type,
    )
    assert result == audio
    assert mime_type == "audio/ogg"
    assert http.calls[0]["url"].endswith(
        f"/chat/getBase64FromMediaMessage/{adapter.instance_name}"
    )
    assert http.calls[0]["json_body"]["message"]["key"] == {
        "id": "audio-1",
        "remoteJid": "5511999999999@s.whatsapp.net",
        "fromMe": False,
    }


def test_audio_rejeita_referencia_adulterada_e_conteudo_acima_do_limite() -> None:
    adapter = _adapter(HTTPFake([]))
    with pytest.raises(ErroProvedorExterno, match="referencia"):
        adapter.baixar_audio_whatsapp(media_id="evomedia.e30.assinatura")

    reference = adapter._criar_referencia_midia(
        message_id="audio-2", remote_jid="5511999999999@s.whatsapp.net"
    )
    adapter = _adapter(
        HTTPFake(
            [
                RespostaProvedor(
                    status_code=200,
                    payload={
                        "base64": base64.b64encode(b"grande").decode(),
                        "mimetype": "audio/ogg",
                    },
                )
            ]
        )
    )
    with pytest.raises(ErroProvedorExterno, match="excede"):
        adapter.baixar_audio_whatsapp(media_id=reference, max_bytes=2)
