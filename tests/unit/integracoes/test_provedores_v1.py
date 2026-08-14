from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal
from typing import Any

import pytest

from core.integracoes.provedores import (
    ConfiguracaoGeminiTenant,
    ConfiguracaoMercadoPago,
    ConfiguracaoMeta,
    ErroProvedorExterno,
    ErroProvedorTransitorio,
    GeminiTenantAdapter,
    MercadoPagoAdapter,
    MetaAdapter,
    RespostaProvedor,
)


class HTTPFixture:
    def __init__(self, respostas: list[RespostaProvedor | Exception]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict[str, Any]] = []

    def request(self, **kwargs: Any) -> RespostaProvedor:
        self.chamadas.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def test_meta_cobre_whatsapp_facebook_instagram_e_assinatura() -> None:
    http = HTTPFixture(
        [
            RespostaProvedor(
                status_code=200, payload={"messages": [{"id": "wamid-1"}]}
            ),
            RespostaProvedor(status_code=200, payload={"id": "post-1"}),
            RespostaProvedor(status_code=200, payload={"id": "container-1"}),
            RespostaProvedor(status_code=200, payload={"id": "media-1"}),
        ]
    )
    config = ConfiguracaoMeta(
        servico="mensageria.whatsapp",
        access_token="access-secret",
        app_secret="app-secret",
        app_id="app-1",
        phone_number_id="phone-1",
        webhook_verify_token="verify-secret",
    )
    whatsapp = MetaAdapter(configuracao=config, http=http)

    assert whatsapp.enviar_whatsapp(
        destinatario="5511999999999", texto="Ola", idempotency_key="msg-1"
    ) == "wamid-1"
    facebook = MetaAdapter(
        configuracao=ConfiguracaoMeta(
            servico="social.facebook",
            access_token="access-secret",
            app_secret="app-secret",
            app_id="app-1",
            page_id="page-1",
        ),
        http=http,
    )
    assert facebook.publicar_facebook(
        mensagem="Oferta", idempotency_key="post-1"
    ) == "post-1"
    instagram = MetaAdapter(
        configuracao=ConfiguracaoMeta(
            servico="social.instagram",
            access_token="access-secret",
            app_secret="app-secret",
            app_id="app-1",
            business_account_id="ig-1",
        ),
        http=http,
    )
    assert instagram.publicar_instagram(
        image_url="https://example.test/a.jpg",
        legenda="Oferta",
        idempotency_key="media-1",
    ) == "media-1"
    payload = (
        b'{"object":"whatsapp_business_account","entry":[{"id":"waba-1",'
        b'"changes":[{"field":"messages","value":{"messages":[{"id":'
        b'"wamid-in-1"}]}}]}]}'
    )
    assinatura = "sha256=" + hmac.new(b"app-secret", payload, hashlib.sha256).hexdigest()
    assert whatsapp.validar_webhook(payload, assinatura) is True
    evento = whatsapp.normalizar_webhook(
        payload_bruto=payload, assinatura=assinatura
    )[0]
    assert evento.recurso_id == "wamid-in-1"
    assert evento.idempotency_key == "meta:waba-1:messages:wamid-in-1:mensagem"
    assert whatsapp.validar_desafio(verify_token="verify-secret", challenge="123") == "123"
    assert http.chamadas[0]["json_body"]["biz_opaque_callback_data"] == "msg-1"
    assert "access-secret" not in repr(config)
    assert "app-secret" not in repr(config)

    with pytest.raises(ErroProvedorExterno, match="nao autorizado"):
        facebook.enviar_whatsapp(
            destinatario="5511999999999", texto="x", idempotency_key="cross-1"
        )


def test_mercado_pago_pix_idempotente_e_webhook_hmac() -> None:
    http = HTTPFixture(
        [
                RespostaProvedor(
                    status_code=201,
                    payload={
                        "id": 42,
                        "status": "pending",
                        "transaction_amount": "10.50",
                        "external_reference": "pedido-1",
                        "point_of_interaction": {
                            "transaction_data": {
                                "qr_code": "000201PIX",
                                "ticket_url": "https://mercadopago.test/ticket/42",
                            }
                        },
                    },
                )
        ]
    )
    config = ConfiguracaoMercadoPago(
        access_token="mp-access",
        webhook_secret="mp-webhook",
        notification_url="https://homolog.example/webhooks/mercado-pago",
    )
    adapter = MercadoPagoAdapter(configuracao=config, http=http)
    cobranca = adapter.criar_pix(
        valor=Decimal("10.50"),
        email_pagador="cliente@example.test",
        referencia_externa="pedido-1",
        idempotency_key="idem-1",
    )
    assert cobranca.pagamento_id == "42"
    assert cobranca.pix_copia_cola == "000201PIX"
    assert http.chamadas[0]["headers"]["X-Idempotency-Key"] == "idem-1"

    manifesto = "id:42;request-id:req-1;ts:1710000000;"
    digest = hmac.new(b"mp-webhook", manifesto.encode(), hashlib.sha256).hexdigest()
    assert adapter.validar_webhook(
        data_id="42",
        request_id="req-1",
        x_signature=f"ts=1710000000,v1={digest}",
    )
    assert not adapter.validar_webhook(
        data_id="42", request_id="req-1", x_signature="ts=1710000000,v1=invalida"
    )
    evento = adapter.normalizar_webhook(
        payload={"id": "evt-1", "action": "payment.updated"},
        data_id="42",
        request_id="req-1",
        x_signature=f"ts=1710000000,v1={digest}",
    )
    assert evento.idempotency_key == "mercado_pago:evt-1:42:payment.updated"


class GeminiFixture:
    def __init__(self) -> None:
        self.tentativas = 0
        self.chamadas: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.tentativas += 1
        self.chamadas.append(kwargs)
        if self.tentativas < 3:
            raise TimeoutError("gemini-secret")
        return {"text": "ok"}


def test_gemini_por_tenant_aplica_timeout_retry_e_nao_expoe_chave() -> None:
    gateway = GeminiFixture()
    sleeps: list[float] = []
    config = ConfiguracaoGeminiTenant(api_key="gemini-secret", model="gemini-test")
    adapter = GeminiTenantAdapter(
        configuracao=config, gateway=gateway, sleep=sleeps.append
    )
    assert adapter.gerar("analise") == {"text": "ok"}
    assert sleeps == [0.25, 0.5]
    assert gateway.chamadas[-1]["api_key"] == "gemini-secret"
    assert "gemini-secret" not in repr(config)


def test_retry_esgotado_sanitiza_excecao_do_provedor() -> None:
    http = HTTPFixture([TimeoutError("access-secret")] * 3)
    adapter = MetaAdapter(
        configuracao=ConfiguracaoMeta(
            servico="social.facebook",
            access_token="access-secret",
            app_secret="app-secret",
            app_id="app-1",
            page_id="page-1",
        ),
        http=http,
    )
    with pytest.raises(ErroProvedorTransitorio) as capturado:
        adapter.publicar_facebook(mensagem="x", idempotency_key="post-timeout")
    assert "access-secret" not in str(capturado.value)
    assert "reconciliacao obrigatoria" in str(capturado.value)
    assert len(http.chamadas) == 1
