from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.pagbank import (
    AdapterPagBank,
    ClientePagBank,
    ConfiguracaoPagBank,
    ErroPagBank,
)


class _Resposta:
    def __init__(self, status_code: int, payload) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class _Transporte:
    def __init__(self, respostas: list[_Resposta]) -> None:
        self.respostas = list(respostas)
        self.chamadas: list[dict] = []

    def request(self, method, url, *, headers, json=None, timeout):
        self.chamadas.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "json": json,
                "timeout": timeout,
            }
        )
        return self.respostas.pop(0)


def _payload_order() -> dict:
    return {
        "id": "ORDE_TESTE_123",
        "charges": [
            {
                "id": "CHAR_TESTE_123",
                "status": "PAID",
                "amount": {"value": 2590},
                "paid_at": "2026-08-18T01:00:00Z",
            }
        ],
        "qr_codes": [
            {
                "amount": {"value": 2590},
                "text": "000201PIXTESTE",
                "links": [
                    {
                        "media": "image/png",
                        "href": "https://example.test/qr.png",
                    }
                ],
            }
        ],
    }


def test_pagbank_cria_pix_com_idempotencia_notification_url_e_sem_expor_token() -> None:
    transporte = _Transporte([_Resposta(201, _payload_order())])
    token = "token-pagbank-super-secreto"
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(
            token=token,
            ambiente="sandbox",
            notification_url="https://example.test/webhooks/pagbank",
            timeout_seconds=9,
        ),
        transporte=transporte,
    )

    cobranca = adapter.criar_pix(
        pagamento_id="pedido-123",
        valor=Dinheiro(Decimal("25.90")),
        idempotency_key="idem-pedido-123",
        cliente=ClientePagBank(
            nome="Cliente Teste",
            email="cliente@example.test",
            tax_id="123.456.789-09",
        ),
    )

    chamada = transporte.chamadas[0]
    assert chamada["method"] == "POST"
    assert chamada["url"] == "https://sandbox.api.pagseguro.com/orders"
    assert chamada["headers"]["x-idempotency-key"] == "idem-pedido-123"
    assert chamada["headers"]["Authorization"] == f"Bearer {token}"
    assert chamada["json"]["notification_urls"] == [
        "https://example.test/webhooks/pagbank"
    ]
    assert chamada["json"]["qr_codes"][0]["amount"]["value"] == 2590
    assert cobranca.id_externo == "ORDE_TESTE_123"
    assert cobranca.status == "pago"
    assert token not in repr(adapter)


def test_pagbank_webhook_so_e_confiavel_com_assinatura_valida() -> None:
    token = "token-webhook-secreto"
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token=token, ambiente="sandbox"),
        transporte=_Transporte([]),
    )
    payload = json.dumps(_payload_order(), separators=(",", ":")).encode("utf-8")
    assinatura = hashlib.sha256(token.encode("utf-8") + b"-" + payload).hexdigest()

    evento = adapter.normalizar_webhook_assinado(
        payload_bruto=payload,
        assinatura=assinatura,
    )
    assert evento.assinatura_validada is True
    assert evento.provedor == "pagbank"
    assert evento.id_externo == "ORDE_TESTE_123"

    evento_invalido = adapter.normalizar_webhook_assinado(
        payload_bruto=payload,
        assinatura="0" * 64,
    )
    assert evento_invalido.assinatura_validada is False


def test_pagbank_erro_http_e_sanitizado_sem_token_nem_descricao_do_provedor() -> None:
    token = "token-nao-pode-vazar"
    transporte = _Transporte(
        [
            _Resposta(
                400,
                {
                    "error_messages": [
                        {
                            "code": "40001",
                            "parameter_name": "customer.tax_id",
                            "description": f"valor invalido usando {token}",
                        }
                    ]
                },
            )
        ]
    )
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token=token, ambiente="sandbox"),
        transporte=transporte,
    )

    with pytest.raises(ErroPagBank) as exc_info:
        adapter.criar_pix(
            pagamento_id="pedido-erro",
            valor=Dinheiro(Decimal("10.00")),
            idempotency_key="idem-erro",
            cliente=ClientePagBank(
                nome="Cliente Teste",
                email="cliente@example.test",
                tax_id="12345678909",
            ),
        )

    mensagem = str(exc_info.value)
    assert "HTTP 400" in mensagem
    assert "code=40001" in mensagem
    assert "parameter=customer.tax_id" in mensagem
    assert token not in mensagem
    assert "description" not in mensagem.casefold()
