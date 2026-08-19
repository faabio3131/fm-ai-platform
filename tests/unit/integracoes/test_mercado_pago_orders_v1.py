from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal

import pytest

from core.integracoes.provedores import (
    ConfiguracaoMercadoPago,
    ErroProvedorExterno,
    MercadoPagoAdapter,
    RespostaProvedor,
)
from scripts.wire_mercado_pago_orders_v1 import apply


class _HTTP:
    def __init__(self, respostas: list[RespostaProvedor]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.respostas.pop(0)


def _config() -> ConfiguracaoMercadoPago:
    return ConfiguracaoMercadoPago(
        access_token="token-teste",
        webhook_secret="segredo-webhook",
        notification_url="https://example.invalid/webhooks/mercado-pago",
    )


def _order(*, status: str = "action_required", detail: str = "waiting_transfer"):
    return {
        "id": "ORD01TEST",
        "type": "online",
        "total_amount": "31.90",
        "external_reference": "pag-123",
        "status": status,
        "status_detail": detail,
        "transactions": {
            "payments": [
                {
                    "id": "PAY01TEST",
                    "amount": "31.90",
                    "status": status,
                    "status_detail": detail,
                    "payment_method": {
                        "id": "pix",
                        "type": "bank_transfer",
                        "ticket_url": "https://example.invalid/ticket",
                        "qr_code": "000201-orders",
                        "qr_code_base64": "base64-orders",
                    },
                }
            ]
        },
    }


def test_criar_pix_usa_orders_e_idempotencia() -> None:
    http = _HTTP([RespostaProvedor(status_code=201, payload=_order())])
    adapter = MercadoPagoAdapter(configuracao=_config(), http=http)

    cobranca = adapter.criar_pix(
        valor=Decimal("31.90"),
        email_pagador="cliente@example.com",
        referencia_externa="pag-123",
        idempotency_key="idem-123",
    )

    chamada = http.chamadas[0]
    assert chamada["method"] == "POST"
    assert chamada["url"] == "https://api.mercadopago.com/v1/orders"
    assert chamada["headers"]["X-Idempotency-Key"] == "idem-123"
    body = chamada["json_body"]
    assert body["type"] == "online"
    assert body["processing_mode"] == "automatic"
    assert body["total_amount"] == "31.90"
    assert body["transactions"]["payments"][0]["payment_method"] == {
        "id": "pix",
        "type": "bank_transfer",
    }
    assert "notification_url" not in body
    assert cobranca.pagamento_id == "ORD01TEST"
    assert cobranca.pix_copia_cola == "000201-orders"
    assert cobranca.qr_code_base64 == "base64-orders"


def test_consulta_order_e_mapeia_accredited_para_paid() -> None:
    http = _HTTP(
        [RespostaProvedor(status_code=200, payload=_order(status="processed", detail="accredited"))]
    )
    adapter = MercadoPagoAdapter(configuracao=_config(), http=http)

    cobranca = adapter.consultar_pagamento("ORD01TEST")

    assert http.chamadas[0]["url"] == "https://api.mercadopago.com/v1/orders/ORD01TEST"
    assert cobranca.status == "paid"
    assert cobranca.valor == Decimal("31.90")


def test_processed_nao_accredited_nao_liquida() -> None:
    http = _HTTP([])
    adapter = MercadoPagoAdapter(configuracao=_config(), http=http)
    cobranca = adapter._normalizar(_order(status="processed", detail="partially_refunded"))
    assert cobranca.status == "processed"


def test_webhook_orders_valida_assinatura_e_recurso_preservando_case_do_data_id() -> None:
    adapter = MercadoPagoAdapter(configuracao=_config(), http=_HTTP([]))
    data_id = "ORD01TEST"
    request_id = "req-123"
    ts = "1755600000"
    # O SDK/documentacao oficial usa exatamente o data.id recebido no query param.
    # Orders usa IDs alfanumericos em maiusculas; mudar o case quebra o HMAC real.
    manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    digest = hmac.new(b"segredo-webhook", manifesto.encode(), hashlib.sha256).hexdigest()
    assinatura = f"ts={ts},v1={digest}"
    payload = {
        "type": "order",
        "action": "order.updated",
        "data": {"id": data_id},
    }

    evento = adapter.normalizar_webhook(
        payload=payload,
        data_id=data_id,
        request_id=request_id,
        x_signature=assinatura,
    )
    assert evento.recurso_id == data_id
    assert evento.tipo == "order.updated"
    assert evento.assinatura_validada is True

    with pytest.raises(ErroProvedorExterno):
        adapter.normalizar_webhook(
            payload={"type": "order", "data": {"id": "ORD-DIVERGENTE"}},
            data_id=data_id,
            request_id=request_id,
            x_signature=assinatura,
        )


def test_patch_orders_e_idempotente() -> None:
    original = "prefix\nclass MercadoPagoAdapter(_ClienteResiliente):\nLEGADO\n\nclass PortaGeminiTenant(Protocol):\nsuffix\n"
    primeiro = apply(original)
    segundo = apply(primeiro)
    assert primeiro == segundo
    assert '/v1/orders"' in primeiro
    assert "/v1/payments" not in primeiro
    assert "data_id.lower()" not in primeiro
    assert 'manifesto = f"id:{data_id};request-id:{request_id};ts:{ts};"' in primeiro
