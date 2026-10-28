"""Adapter da Evolution API v2 para WhatsApp por instância isolada.

QR e segredos nunca são persistidos por este adapter. Operações mutáveis não
são repetidas porque um timeout pode ocorrer depois de a Evolution aceitá-las.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from core.integracoes.provedores import (
    ErroProvedorExterno,
    ErroProvedorTransitorio,
    MensagemWhatsAppEntrada,
    PortaHTTPProvedor,
)

_INSTANCE = re.compile(r"kord-[a-f0-9]{32}\Z")
_PHONE_JID = re.compile(r"^([0-9]{10,15})@s\.whatsapp\.net$")
_PNG = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True, repr=False, kw_only=True)
class ConfiguracaoEvolution:
    base_url: str
    api_key: str
    webhook_token: str
    instance_name: str
    timeout_seconds: float = 8.0

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("base_url Evolution deve usar HTTPS")
        if not self.api_key.strip() or len(self.webhook_token) < 32:
            raise ValueError("credencial Evolution ausente")
        if not _INSTANCE.fullmatch(self.instance_name):
            raise ValueError("instancia Evolution invalida")

    def __repr__(self) -> str:
        return (
            f"ConfiguracaoEvolution(instance_name={self.instance_name!r}, api_key=***)"
        )


class EvolutionAdapter:
    provedor = "evolution"

    def __init__(
        self, *, configuracao: ConfiguracaoEvolution, http: PortaHTTPProvedor
    ) -> None:
        self._config = configuracao
        self._http = http

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        try:
            response = self._http.request(
                method=method,
                url=f"{self._config.base_url.rstrip('/')}{path}",
                headers={
                    "apikey": self._config.api_key,
                    "Content-Type": "application/json",
                },
                json_body=body,
                timeout_seconds=self._config.timeout_seconds,
            )
        except (TimeoutError, ConnectionError) as exc:
            raise ErroProvedorTransitorio(
                "Evolution indisponivel; reconciliacao obrigatoria"
            ) from exc
        if response.status_code == 404:
            raise ErroProvedorExterno("instancia Evolution inexistente")
        if response.status_code >= 500:
            raise ErroProvedorTransitorio(
                f"Evolution HTTP {response.status_code}; reconciliacao obrigatoria"
            )
        if not 200 <= response.status_code < 300:
            raise ErroProvedorExterno(
                f"Evolution rejeitou requisicao HTTP {response.status_code}"
            )
        if not isinstance(response.payload, Mapping):
            raise ErroProvedorExterno("Evolution retornou payload invalido")
        return response.payload

    @property
    def instance_name(self) -> str:
        return self._config.instance_name

    def estado(self) -> str:
        payload = self._request(
            "GET", f"/instance/connectionState/{self._config.instance_name}"
        )
        instance = payload.get("instance")
        if (
            not isinstance(instance, Mapping)
            or instance.get("instanceName") != self._config.instance_name
        ):
            raise ErroProvedorExterno("estado Evolution nao corresponde a instancia")
        state = str(instance.get("state", ""))
        if state not in {"open", "close", "connecting"}:
            raise ErroProvedorExterno("estado Evolution invalido")
        return state

    def criar_instancia(self) -> None:
        self._request(
            "POST",
            "/instance/create",
            body={
                "instanceName": self._config.instance_name,
                "qrcode": True,
                "integration": "WHATSAPP-BAILEYS",
            },
        )

    def configurar_webhook(self, webhook_url: str) -> None:
        if not webhook_url.startswith("https://"):
            raise ErroProvedorExterno("webhook Evolution deve usar HTTPS")
        self._request(
            "POST",
            f"/webhook/set/{self._config.instance_name}",
            body={
                "webhook": {
                    "enabled": True,
                    "url": webhook_url,
                    "byEvents": False,
                    "base64": False,
                    "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE"],
                    "headers": {"x-kordena-evolution-auth": self._config.webhook_token},
                }
            },
        )

    def obter_qr_code(self) -> str:
        payload = self._request(
            "GET", f"/instance/connect/{self._config.instance_name}"
        )
        raw = payload.get("base64")
        if not raw and isinstance(payload.get("qrcode"), Mapping):
            raw = payload["qrcode"].get("base64")  # type: ignore[index]
        if not isinstance(raw, str):
            raise ErroProvedorExterno("Evolution nao retornou QR Code")
        encoded = raw.removeprefix("data:image/png;base64,")
        try:
            image = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ErroProvedorExterno("QR Code Evolution invalido") from exc
        if not image.startswith(_PNG) or len(image) > 160_000:
            raise ErroProvedorExterno("QR Code Evolution fora do formato permitido")
        return f"data:image/png;base64,{encoded}"

    def desconectar(self) -> None:
        self._request("DELETE", f"/instance/logout/{self._config.instance_name}")

    def enviar_whatsapp(
        self, *, destinatario: str, texto: str, idempotency_key: str
    ) -> str:
        del (
            idempotency_key
        )  # Evolution v2 não oferece chave idempotente neste endpoint.
        destino = "".join(char for char in destinatario if char.isdigit())
        if not destino or not texto.strip() or len(texto) > 4000:
            raise ErroProvedorExterno("mensagem WhatsApp incompleta")
        if self.estado() != "open":
            raise ErroProvedorExterno("sessao Evolution desconectada")
        payload = self._request(
            "POST",
            f"/message/sendText/{self._config.instance_name}",
            body={"number": destino, "text": texto.strip()},
        )
        key = payload.get("key")
        message_id = key.get("id") if isinstance(key, Mapping) else None
        if not isinstance(message_id, str) or not message_id.strip():
            raise ErroProvedorExterno("Evolution nao confirmou id da mensagem")
        return message_id

    def extrair_mensagens_whatsapp(
        self, *, payload_bruto: bytes, assinatura: str
    ) -> tuple[MensagemWhatsAppEntrada, ...]:
        if not hmac.compare_digest(self._config.webhook_token, assinatura):
            raise ErroProvedorExterno("autenticacao Evolution invalida")
        try:
            payload = json.loads(payload_bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErroProvedorExterno("webhook Evolution invalido") from exc
        if (
            not isinstance(payload, Mapping)
            or payload.get("instance") != self._config.instance_name
        ):
            raise ErroProvedorExterno("webhook Evolution de instancia divergente")
        if payload.get("event") != "messages.upsert":
            return ()
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ErroProvedorExterno("evento Evolution invalido")
        key = data.get("key")
        message = data.get("message")
        if (
            not isinstance(key, Mapping)
            or not isinstance(message, Mapping)
            or key.get("fromMe") is not False
        ):
            return ()
        match = _PHONE_JID.fullmatch(str(key.get("remoteJid", "")))
        message_id = str(key.get("id", "")).strip()
        if match is None or not message_id:
            return ()
        text = message.get("conversation")
        extended = message.get("extendedTextMessage")
        if not isinstance(text, str) and isinstance(extended, Mapping):
            text = extended.get("text")
        if not isinstance(text, str) or not text.strip():
            return ()
        return (
            MensagemWhatsAppEntrada(
                mensagem_id=f"evo:{message_id}",
                remetente=match.group(1),
                tipo="text",
                timestamp=str(data.get("messageTimestamp", "")),
                texto=text.strip(),
            ),
        )

    def baixar_audio_whatsapp(self, **_: Any) -> tuple[bytes, str]:
        raise ErroProvedorExterno("audio Evolution ainda nao suportado neste adapter")


def nome_instancia_evolution(tenant_id: str, unidade_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}:{unidade_id}".encode()).hexdigest()[:32]
    return f"kord-{digest}"
