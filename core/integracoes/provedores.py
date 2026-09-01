"""Adapters externos configuráveis por tenant para Meta, Mercado Pago e Gemini.

Configuração e segredos chegam resolvidos pela fábrica de infraestrutura. Os
adapters não consultam ambiente global, não persistem credenciais e nunca incluem
payloads ou segredos nas mensagens de erro. Requisições mutáveis sem garantia de
idempotência do provedor não são repetidas automaticamente.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol


class ErroProvedorExterno(RuntimeError):
    """Falha sanitizada de um provedor externo."""


class ErroProvedorTransitorio(ErroProvedorExterno):
    """Falha temporária que pode exigir reconciliação ou retry posterior."""


@dataclass(frozen=True, kw_only=True)
class RespostaProvedor:
    status_code: int
    payload: Mapping[str, Any] | None


@dataclass(frozen=True, kw_only=True)
class RespostaBinariaProvedor:
    status_code: int
    content: bytes
    content_type: str | None = None


class PortaDownloadBinario(Protocol):
    def get(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> RespostaBinariaProvedor: ...


class PortaHTTPProvedor(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        json_body: Mapping[str, Any] | None,
        timeout_seconds: float,
    ) -> RespostaProvedor: ...


@dataclass(frozen=True, kw_only=True)
class EventoWebhookProvedor:
    provedor: str
    evento_id: str
    recurso_id: str
    tipo: str
    assinatura_validada: bool
    idempotency_key: str


@dataclass(frozen=True, kw_only=True)
class MensagemWhatsAppEntrada:
    mensagem_id: str
    remetente: str
    tipo: str
    timestamp: str
    texto: str | None = None
    media_id: str | None = None
    mime_type: str | None = None

    def __post_init__(self) -> None:
        if not self.mensagem_id.strip() or not self.remetente.strip():
            raise ValueError("mensagem_whatsapp_invalida")
        if self.tipo not in {"text", "audio"}:
            return
        if self.tipo == "text" and not (self.texto or "").strip():
            raise ValueError("mensagem_whatsapp_texto_vazio")
        if self.tipo == "audio" and not (self.media_id or "").strip():
            raise ValueError("mensagem_whatsapp_audio_sem_midia")


class _ClienteResiliente:
    _RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})

    def __init__(
        self,
        *,
        http: PortaHTTPProvedor,
        timeout_seconds: float,
        max_attempts: int,
        sleep: Callable[[float], None],
        nome: str,
    ) -> None:
        if not 0 < timeout_seconds <= 30 or not 1 <= max_attempts <= 5:
            raise ValueError("politica de transporte invalida")
        self._http = http
        self._timeout = timeout_seconds
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._nome = nome

    def _request(
        self, *, retry_safe: bool, **kwargs: Any
    ) -> Mapping[str, Any]:
        tentativas = self._max_attempts if retry_safe else 1
        for tentativa in range(1, tentativas + 1):
            try:
                resposta = self._http.request(
                    timeout_seconds=self._timeout, **kwargs
                )
            except (TimeoutError, ConnectionError) as exc:
                if tentativa == tentativas:
                    sufixo = "; reconciliacao obrigatoria" if not retry_safe else ""
                    raise ErroProvedorTransitorio(
                        f"{self._nome} indisponivel{sufixo}"
                    ) from exc
                self._sleep(0.25 * 2 ** (tentativa - 1))
                continue
            if resposta.status_code in self._RETRYABLE:
                if tentativa == tentativas:
                    sufixo = "; reconciliacao obrigatoria" if not retry_safe else ""
                    raise ErroProvedorTransitorio(
                        f"{self._nome} HTTP {resposta.status_code}{sufixo}"
                    )
                self._sleep(0.25 * 2 ** (tentativa - 1))
                continue
            if not 200 <= resposta.status_code < 300:
                raise ErroProvedorExterno(
                    f"{self._nome} rejeitou requisicao HTTP {resposta.status_code}"
                )
            if not isinstance(resposta.payload, Mapping):
                raise ErroProvedorExterno(
                    f"{self._nome} retornou payload invalido"
                )
            return resposta.payload
        raise AssertionError("retry terminou sem resultado")


def _obrigatorio(valor: str | None, nome: str) -> str:
    texto = (valor or "").strip()
    if not texto:
        raise ErroProvedorExterno(f"{nome} ausente na configuracao Meta")
    return texto


def _idempotency_key(valor: str) -> str:
    normalizado = valor.strip()
    if not normalizado or len(normalizado) > 128:
        raise ErroProvedorExterno("idempotency_key invalida")
    return normalizado


@dataclass(frozen=True, repr=False, kw_only=True)
class ConfiguracaoMeta:
    servico: str
    access_token: str
    app_secret: str
    app_id: str
    page_id: str | None = None
    business_account_id: str | None = None
    facebook_page_id: str | None = None
    phone_number_id: str | None = None
    webhook_verify_token: str | None = None
    graph_api_version: str = "v23.0"
    timeout_seconds: float = 8.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.access_token.strip() or not self.app_secret.strip():
            raise ValueError("credencial Meta ausente")
        if not self.app_id.strip() or not self.graph_api_version.startswith("v"):
            raise ValueError("configuracao Meta invalida")

    def __repr__(self) -> str:
        return (
            "ConfiguracaoMeta(access_token=***, app_secret=***, "
            f"servico={self.servico!r}, graph_api_version={self.graph_api_version!r})"
        )


class MetaAdapter(_ClienteResiliente):
    def __init__(
        self,
        *,
        configuracao: ConfiguracaoMeta,
        http: PortaHTTPProvedor,
        media_http: PortaDownloadBinario | None = None,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        super().__init__(
            http=http,
            timeout_seconds=configuracao.timeout_seconds,
            max_attempts=configuracao.max_attempts,
            sleep=sleep,
            nome="Meta",
        )
        self._config = configuracao
        self._media_http = media_http

    def _post(self, recurso: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        # Graph POST pode ter sido processado antes de um timeout. Sem garantia
        # oficial de idempotência, repetir aqui criaria mensagens/posts duplicados.
        return self._request(
            retry_safe=False,
            method="POST",
            url=(
                "https://graph.facebook.com/"
                f"{self._config.graph_api_version}/{recurso}"
            ),
            headers={
                "Authorization": f"Bearer {self._config.access_token}",
                "Content-Type": "application/json",
            },
            json_body=payload,
        )

    def enviar_whatsapp(
        self, *, destinatario: str, texto: str, idempotency_key: str
    ) -> str:
        if self._config.servico != "mensageria.whatsapp":
            raise ErroProvedorExterno("adapter Meta nao autorizado para WhatsApp")
        phone_number_id = _obrigatorio(
            self._config.phone_number_id, "phone_number_id"
        )
        destino = "".join(c for c in destinatario if c.isdigit())
        if not destino or not texto.strip():
            raise ErroProvedorExterno("mensagem WhatsApp incompleta")
        resposta = self._post(
            f"{phone_number_id}/messages",
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "text",
                "text": {"preview_url": False, "body": texto.strip()},
                "biz_opaque_callback_data": _idempotency_key(idempotency_key),
            },
        )
        try:
            return str(resposta["messages"][0]["id"])  # type: ignore[index]
        except (IndexError, KeyError, TypeError) as exc:
            raise ErroProvedorExterno("Meta nao retornou id da mensagem") from exc

    def publicar_facebook(self, *, mensagem: str, idempotency_key: str) -> str:
        if self._config.servico != "social.facebook":
            raise ErroProvedorExterno("adapter Meta nao autorizado para Facebook")
        page_id = _obrigatorio(self._config.page_id, "page_id")
        if not mensagem.strip():
            raise ErroProvedorExterno("mensagem Facebook vazia")
        _idempotency_key(idempotency_key)
        resposta = self._post(f"{page_id}/feed", {"message": mensagem.strip()})
        identificador = str(resposta.get("id", "")).strip()
        if not identificador:
            raise ErroProvedorExterno("Meta nao retornou id da publicacao")
        return identificador

    def publicar_instagram(
        self, *, image_url: str, legenda: str, idempotency_key: str
    ) -> str:
        if self._config.servico != "social.instagram":
            raise ErroProvedorExterno("adapter Meta nao autorizado para Instagram")
        business_account_id = _obrigatorio(
            self._config.business_account_id, "business_account_id"
        )
        if not image_url.startswith("https://"):
            raise ErroProvedorExterno("image_url Instagram deve usar HTTPS")
        _idempotency_key(idempotency_key)
        container = self._post(
            f"{business_account_id}/media",
            {"image_url": image_url, "caption": legenda.strip()},
        )
        creation_id = str(container.get("id", "")).strip()
        if not creation_id:
            raise ErroProvedorExterno("Meta nao retornou container Instagram")
        publicado = self._post(
            f"{business_account_id}/media_publish", {"creation_id": creation_id}
        )
        media_id = str(publicado.get("id", "")).strip()
        if not media_id:
            raise ErroProvedorExterno("Meta nao retornou id Instagram")
        return media_id

    def validar_webhook(self, payload_bruto: bytes, assinatura: str) -> bool:
        recebido = assinatura.removeprefix("sha256=").strip().casefold()
        esperado = hmac.new(
            self._config.app_secret.encode(), payload_bruto, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(esperado, recebido)

    def extrair_mensagens_whatsapp(
        self,
        *,
        payload_bruto: bytes,
        assinatura: str,
    ) -> tuple[MensagemWhatsAppEntrada, ...]:
        if self._config.servico != "mensageria.whatsapp":
            raise ErroProvedorExterno("adapter Meta nao autorizado para WhatsApp")
        if not self.validar_webhook(payload_bruto, assinatura):
            raise ErroProvedorExterno("assinatura Meta invalida")
        try:
            payload = json.loads(payload_bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErroProvedorExterno("webhook Meta invalido") from exc
        if not isinstance(payload, Mapping):
            raise ErroProvedorExterno("webhook Meta invalido")

        mensagens: list[MensagemWhatsAppEntrada] = []
        entries = payload.get("entry")
        if not isinstance(entries, list):
            return ()
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, Mapping):
                    continue
                value = change.get("value")
                if not isinstance(value, Mapping):
                    continue
                itens = value.get("messages")
                if not isinstance(itens, list):
                    continue
                for item in itens:
                    if not isinstance(item, Mapping):
                        continue
                    mensagem_id = str(item.get("id", "")).strip()
                    remetente = str(item.get("from", "")).strip()
                    tipo = str(item.get("type", "")).strip().casefold()
                    timestamp = str(item.get("timestamp", "")).strip()
                    if not mensagem_id or not remetente:
                        continue
                    texto = None
                    media_id = None
                    mime_type = None
                    if tipo == "text":
                        payload_texto = item.get("text")
                        if isinstance(payload_texto, Mapping):
                            texto = str(payload_texto.get("body", "")).strip() or None
                    elif tipo == "audio":
                        payload_audio = item.get("audio")
                        if isinstance(payload_audio, Mapping):
                            media_id = str(payload_audio.get("id", "")).strip() or None
                            mime_type = (
                                str(payload_audio.get("mime_type", "")).strip() or None
                            )
                    mensagens.append(
                        MensagemWhatsAppEntrada(
                            mensagem_id=mensagem_id,
                            remetente=remetente,
                            tipo=tipo or "desconhecido",
                            timestamp=timestamp,
                            texto=texto,
                            media_id=media_id,
                            mime_type=mime_type,
                        )
                    )
        return tuple(mensagens)

    def baixar_audio_whatsapp(
        self,
        *,
        media_id: str,
        mime_type_declarado: str | None = None,
        max_bytes: int = 20 * 1024 * 1024,
    ) -> tuple[bytes, str]:
        if self._config.servico != "mensageria.whatsapp":
            raise ErroProvedorExterno("adapter Meta nao autorizado para WhatsApp")
        if self._media_http is None:
            raise ErroProvedorExterno("transporte de midia WhatsApp indisponivel")
        identificador = media_id.strip()
        if not identificador:
            raise ErroProvedorExterno("media_id WhatsApp ausente")
        metadata = self._request(
            retry_safe=True,
            method="GET",
            url=(
                "https://graph.facebook.com/"
                f"{self._config.graph_api_version}/{identificador}"
            ),
            headers={"Authorization": f"Bearer {self._config.access_token}"},
            json_body=None,
        )
        url = str(metadata.get("url", "")).strip()
        mime_type = str(
            metadata.get("mime_type") or mime_type_declarado or ""
        ).strip().casefold()
        try:
            tamanho = int(metadata.get("file_size") or 0)
        except (TypeError, ValueError) as exc:
            raise ErroProvedorExterno("tamanho de midia WhatsApp invalido") from exc
        if not url.startswith("https://") or not mime_type.startswith("audio/"):
            raise ErroProvedorExterno("midia WhatsApp nao autorizada")
        if tamanho < 0 or tamanho > max_bytes:
            raise ErroProvedorExterno("audio WhatsApp excede limite")

        resposta = self._media_http.get(
            url=url,
            headers={"Authorization": f"Bearer {self._config.access_token}"},
            timeout_seconds=self._config.timeout_seconds,
        )
        if not 200 <= resposta.status_code < 300:
            raise ErroProvedorExterno(
                f"Meta rejeitou download de midia HTTP {resposta.status_code}"
            )
        if not resposta.content or len(resposta.content) > max_bytes:
            raise ErroProvedorExterno("audio WhatsApp vazio ou excede limite")
        content_type = (resposta.content_type or mime_type).split(";", 1)[0].strip().casefold()
        if not content_type.startswith("audio/"):
            raise ErroProvedorExterno("conteudo de midia WhatsApp nao e audio")
        return resposta.content, content_type

    def normalizar_webhook(
        self, *, payload_bruto: bytes, assinatura: str
    ) -> tuple[EventoWebhookProvedor, ...]:
        if not self.validar_webhook(payload_bruto, assinatura):
            raise ErroProvedorExterno("assinatura Meta invalida")
        try:
            payload = json.loads(payload_bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErroProvedorExterno("webhook Meta invalido") from exc
        if not isinstance(payload, Mapping):
            raise ErroProvedorExterno("webhook Meta invalido")

        normalizados: list[EventoWebhookProvedor] = []
        entries = payload.get("entry")
        if not isinstance(entries, list):
            return ()
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            entry_id = str(entry.get("id", "")).strip()
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, Mapping):
                    continue
                field = str(change.get("field", "evento")).strip() or "evento"
                value = change.get("value")
                if not isinstance(value, Mapping):
                    continue
                recursos: list[tuple[str, str]] = []
                for chave, tipo in (("messages", "mensagem"), ("statuses", "status")):
                    itens = value.get(chave)
                    if isinstance(itens, list):
                        for item in itens:
                            if isinstance(item, Mapping) and item.get("id"):
                                recursos.append((str(item["id"]), tipo))
                if not recursos:
                    recurso = str(
                        value.get("post_id")
                        or value.get("media_id")
                        or value.get("id")
                        or entry_id
                    ).strip()
                    if recurso:
                        recursos.append((recurso, field))
                for recurso_id, tipo in recursos:
                    evento_id = f"{entry_id}:{field}:{recurso_id}:{tipo}"
                    normalizados.append(
                        EventoWebhookProvedor(
                            provedor="meta",
                            evento_id=evento_id,
                            recurso_id=recurso_id,
                            tipo=tipo,
                            assinatura_validada=True,
                            idempotency_key=f"meta:{evento_id}",
                        )
                    )
        return tuple(normalizados)

    def validar_desafio(self, *, verify_token: str, challenge: str) -> str:
        esperado = self._config.webhook_verify_token or ""
        if not esperado or not hmac.compare_digest(esperado, verify_token):
            raise ErroProvedorExterno("token de verificacao Meta invalido")
        return challenge


@dataclass(frozen=True, repr=False, kw_only=True)
class ConfiguracaoMercadoPago:
    access_token: str
    webhook_secret: str
    notification_url: str
    timeout_seconds: float = 8.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.access_token.strip() or not self.webhook_secret.strip():
            raise ValueError("credencial Mercado Pago ausente")
        if not self.notification_url.startswith("https://"):
            raise ValueError("notification_url Mercado Pago deve usar HTTPS")

    def __repr__(self) -> str:
        return "ConfiguracaoMercadoPago(access_token=***, webhook_secret=***)"


@dataclass(frozen=True, kw_only=True)
class CobrancaMercadoPago:
    pagamento_id: str
    status: str
    valor: Decimal
    referencia_externa: str
    pix_copia_cola: str | None = None
    qr_code_base64: str | None = None
    ticket_url: str | None = None


class MercadoPagoAdapter(_ClienteResiliente):
    """Pix via Checkout Transparente / Orders API do Mercado Pago."""

    BASE_URL = "https://api.mercadopago.com"

    def __init__(
        self,
        *,
        configuracao: ConfiguracaoMercadoPago,
        http: PortaHTTPProvedor,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        super().__init__(
            http=http,
            timeout_seconds=configuracao.timeout_seconds,
            max_attempts=configuracao.max_attempts,
            sleep=sleep,
            nome="Mercado Pago",
        )
        self._config = configuracao

    def _headers(self, idempotency_key: str | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._config.access_token}",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            headers["X-Idempotency-Key"] = _idempotency_key(idempotency_key)
        return headers

    @staticmethod
    def _primeiro_pagamento(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        transacoes = payload.get("transactions")
        if not isinstance(transacoes, Mapping):
            return {}
        pagamentos = transacoes.get("payments")
        if not isinstance(pagamentos, list) or not pagamentos:
            return {}
        primeiro = pagamentos[0]
        return primeiro if isinstance(primeiro, Mapping) else {}

    @staticmethod
    def _status_runtime(payload: Mapping[str, Any], pagamento: Mapping[str, Any]) -> str:
        status = str(payload.get("status", "")).strip().casefold()
        detalhe = str(payload.get("status_detail", "")).strip().casefold()
        if not detalhe:
            detalhe = str(pagamento.get("status_detail", "")).strip().casefold()
        # Orders considera processed/accredited como pagamento efetivamente creditado.
        # O runtime financeiro existente reconhece "paid" como estado liquidado.
        if status == "processed" and detalhe == "accredited":
            return "paid"
        return status

    @classmethod
    def _normalizar(cls, payload: Mapping[str, Any]) -> CobrancaMercadoPago:
        identificador = str(payload.get("id", "")).strip()
        try:
            valor = Decimal(str(payload["total_amount"])).quantize(Decimal("0.01"))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise ErroProvedorExterno("Mercado Pago retornou valor invalido") from exc
        if not identificador or valor <= 0:
            raise ErroProvedorExterno("Mercado Pago retornou order incompleta")

        pagamento = cls._primeiro_pagamento(payload)
        metodo = pagamento.get("payment_method")
        metodo = metodo if isinstance(metodo, Mapping) else {}
        return CobrancaMercadoPago(
            pagamento_id=identificador,
            status=cls._status_runtime(payload, pagamento),
            valor=valor,
            referencia_externa=str(payload.get("external_reference", "")).strip(),
            pix_copia_cola=(str(metodo["qr_code"]) if metodo.get("qr_code") else None),
            qr_code_base64=(
                str(metodo["qr_code_base64"]) if metodo.get("qr_code_base64") else None
            ),
            ticket_url=(str(metodo["ticket_url"]) if metodo.get("ticket_url") else None),
        )

    def criar_pix(
        self,
        *,
        valor: Decimal,
        email_pagador: str,
        referencia_externa: str,
        idempotency_key: str,
    ) -> CobrancaMercadoPago:
        if valor <= 0 or not email_pagador.strip() or not referencia_externa.strip():
            raise ErroProvedorExterno("pagamento Mercado Pago incompleto")
        quantizado = str(valor.quantize(Decimal("0.01")))
        payload = self._request(
            # Orders exige X-Idempotency-Key e permite repeticao segura da criacao.
            retry_safe=True,
            method="POST",
            url=f"{self.BASE_URL}/v1/orders",
            headers=self._headers(idempotency_key),
            json_body={
                "type": "online",
                "total_amount": quantizado,
                "external_reference": referencia_externa.strip(),
                "processing_mode": "automatic",
                "transactions": {
                    "payments": [
                        {
                            "amount": quantizado,
                            "payment_method": {"id": "pix", "type": "bank_transfer"},
                        }
                    ]
                },
                "payer": {"email": email_pagador.strip()},
            },
        )
        return self._normalizar(payload)

    def consultar_pagamento(self, pagamento_id: str) -> CobrancaMercadoPago:
        identificador = pagamento_id.strip()
        if not identificador:
            raise ErroProvedorExterno("order Mercado Pago ausente")
        payload = self._request(
            retry_safe=True,
            method="GET",
            url=f"{self.BASE_URL}/v1/orders/{identificador}",
            headers=self._headers(),
            json_body=None,
        )
        return self._normalizar(payload)

    def validar_webhook(
        self,
        *,
        data_id: str,
        request_id: str,
        x_signature: str,
    ) -> bool:
        partes = {
            chave.strip(): valor.strip()
            for item in x_signature.split(",")
            if "=" in item
            for chave, valor in (item.split("=", 1),)
        }
        ts = partes.get("ts", "").strip()
        recebido = partes.get("v1", "").strip().casefold()
        if not ts or not recebido or not data_id or not request_id:
            return False
        manifesto = f"id:{data_id.strip()};request-id:{request_id};ts:{ts};"
        esperado = hmac.new(
            self._config.webhook_secret.encode(), manifesto.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(esperado, recebido)

    def normalizar_webhook(
        self,
        *,
        payload: Mapping[str, Any],
        data_id: str,
        request_id: str,
        x_signature: str,
    ) -> EventoWebhookProvedor:
        if not self.validar_webhook(
            data_id=data_id, request_id=request_id, x_signature=x_signature
        ):
            raise ErroProvedorExterno("assinatura Mercado Pago invalida")

        tipo = str(payload.get("type") or "").strip().casefold()
        if tipo and tipo != "order":
            raise ErroProvedorExterno("webhook Mercado Pago nao e de order")
        data = payload.get("data")
        body_id = ""
        if isinstance(data, Mapping):
            body_id = str(data.get("id") or "").strip()
        if body_id and body_id.casefold() != data_id.strip().casefold():
            raise ErroProvedorExterno("webhook Mercado Pago com recurso divergente")

        action = str(payload.get("action") or "order.updated").strip()
        evento_id = str(payload.get("id") or request_id).strip()
        if not evento_id or not data_id:
            raise ErroProvedorExterno("webhook Mercado Pago incompleto")
        return EventoWebhookProvedor(
            provedor="mercado_pago",
            evento_id=evento_id,
            recurso_id=data_id.strip(),
            tipo=action,
            assinatura_validada=True,
            idempotency_key=f"mercado_pago:{evento_id}:{data_id.strip()}:{action}",
        )


class PortaGeminiTenant(Protocol):
    def generate_content(
        self, *, api_key: str, model: str, contents: Any, timeout_seconds: float
    ) -> Any: ...


@dataclass(frozen=True, repr=False, kw_only=True)
class ConfiguracaoGeminiTenant:
    api_key: str
    model: str
    timeout_seconds: float = 20.0
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.api_key.strip() or not self.model.strip():
            raise ValueError("configuracao Gemini incompleta")
        if not 0 < self.timeout_seconds <= 60 or not 1 <= self.max_attempts <= 5:
            raise ValueError("politica Gemini invalida")

    def __repr__(self) -> str:
        return f"ConfiguracaoGeminiTenant(api_key=***, model={self.model!r})"


class GeminiTenantAdapter:
    def __init__(
        self,
        *,
        configuracao: ConfiguracaoGeminiTenant,
        gateway: PortaGeminiTenant,
        sleep: Callable[[float], None] = lambda _: None,
    ) -> None:
        self._config = configuracao
        self._gateway = gateway
        self._sleep = sleep

    def gerar(self, contents: Any) -> Any:
        for tentativa in range(1, self._config.max_attempts + 1):
            try:
                return self._gateway.generate_content(
                    api_key=self._config.api_key,
                    model=self._config.model,
                    contents=contents,
                    timeout_seconds=self._config.timeout_seconds,
                )
            except (TimeoutError, ConnectionError) as exc:
                if tentativa == self._config.max_attempts:
                    raise ErroProvedorTransitorio(
                        "Gemini indisponivel apos retries"
                    ) from exc
                self._sleep(0.25 * 2 ** (tentativa - 1))
        raise AssertionError("retry Gemini terminou sem resultado")
