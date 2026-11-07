import hashlib
import json
from datetime import datetime

import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.pagbank import (
    AdapterPagBank,
    ClientePagBank,
    ConfiguracaoPagBank,
    ErroPagBank,
)


class RespostaFake:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


class TransporteFake:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = []

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


def _cliente() -> ClientePagBank:
    return ClientePagBank(
        nome="Cliente Teste",
        email="cliente@example.com",
        tax_id="12345678909",
    )


def _order(*, paid: bool = False):
    charge = (
        [
            {
                "id": "CHAR_1",
                "status": "PAID",
                "paid_at": "2026-08-12T22:10:00-03:00",
                "amount": {"value": 3890, "currency": "BRL"},
            }
        ]
        if paid
        else []
    )
    return {
        "id": "ORDE_1",
        "reference_id": "pay-1",
        "created_at": "2026-08-12T22:00:00-03:00",
        "qr_codes": [
            {
                "amount": {"value": 3890},
                "text": "000201PIXTESTE",
                "links": [
                    {
                        "media": "image/png",
                        "href": "https://api.pagseguro.com/qrcode/teste.png",
                    }
                ],
            }
        ],
        "charges": charge,
    }


def test_cliente_normaliza_tax_id_com_pontuacao() -> None:
    cliente = ClientePagBank(
        nome="Cliente Teste",
        email="cliente@example.com",
        tax_id="123.456.789-09",
    )

    assert cliente.para_payload()["tax_id"] == "12345678909"


def test_cliente_recusa_tax_id_com_tamanho_invalido() -> None:
    cliente = ClientePagBank(
        nome="Cliente Teste",
        email="cliente@example.com",
        tax_id="123",
    )

    with pytest.raises(ValueError, match="11 ou 14"):
        cliente.para_payload()


def test_criar_pix_usa_bearer_idempotencia_centavos_e_qr_code() -> None:
    http = TransporteFake([RespostaFake(201, _order())])
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(
            token="segredo-pagbank",
            ambiente="sandbox",
            notification_url="https://gerente.ai/webhooks/pagbank",
        ),
        transporte=http,
    )

    cobranca = adapter.criar_pix(
        pagamento_id="pay-1",
        valor=Dinheiro("38.90"),
        idempotency_key="idem-1",
        cliente=_cliente(),
        descricao="X-Bacon + Coca",
    )

    assert cobranca.id_externo == "ORDE_1"
    assert cobranca.status == "pendente"
    assert cobranca.valor == Dinheiro("38.90")
    exibicao = dict(cobranca.payload_exibicao)
    assert exibicao["pix_copia_cola"] == "000201PIXTESTE"
    assert exibicao["qr_code_png_url"].endswith("teste.png")

    chamada = http.chamadas[0]
    assert chamada["method"] == "POST"
    assert chamada["url"] == "https://sandbox.api.pagseguro.com/orders"
    assert chamada["headers"]["Authorization"] == "Bearer segredo-pagbank"
    assert chamada["headers"]["x-idempotency-key"] == "idem-1"
    assert chamada["json"]["qr_codes"][0]["amount"]["value"] == 3890
    assert chamada["json"]["items"][0]["unit_amount"] == 3890
    assert chamada["json"]["notification_urls"] == [
        "https://gerente.ai/webhooks/pagbank"
    ]


def test_consultar_order_pago_normaliza_status_e_valor() -> None:
    http = TransporteFake([RespostaFake(200, _order(paid=True))])
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token="token", ambiente="production"), transporte=http
    )

    cobranca = adapter.consultar_transacao("ORDE_1")

    assert cobranca is not None
    assert cobranca.status == "pago"
    assert cobranca.valor == Dinheiro("38.90")
    assert http.chamadas[0]["url"] == "https://api.pagseguro.com/orders/ORDE_1"
    assert adapter.consultar_transacao("id-invalido") is None


def test_webhook_so_e_confiavel_com_payload_bruto_e_assinatura_correta() -> None:
    token = "token-secreto"
    payload = _order(paid=True)
    bruto = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    assinatura = hashlib.sha256(token.encode() + b"-" + bruto).hexdigest()
    adapter = AdapterPagBank(ConfiguracaoPagBank(token=token))

    webhook = adapter.normalizar_webhook_assinado(
        payload_bruto=bruto, assinatura=assinatura
    )

    assert webhook.provedor == "pagbank"
    assert webhook.assinatura_validada is True
    assert webhook.tipo == "confirmado"
    assert webhook.id_externo == "ORDE_1"
    assert webhook.evento_externo == "CHAR_1"
    assert webhook.valor == Dinheiro("38.90")
    assert isinstance(webhook.timestamp, datetime)

    adulterado = adapter.normalizar_webhook_assinado(
        payload_bruto=bruto, assinatura="0" * 64
    )
    assert adulterado.assinatura_validada is False

    # Um dict parseado não preserva os bytes originais e nunca ganha confiança.
    sem_prova = adapter.normalizar_webhook(payload)
    assert sem_prova.assinatura_validada is False


def test_erro_http_e_sanitizado_e_nao_expoe_token() -> None:
    token = "TOKEN-QUE-NAO-PODE-VAZAR"
    http = TransporteFake([RespostaFake(401, {"error": token})])
    adapter = AdapterPagBank(ConfiguracaoPagBank(token=token), transporte=http)

    with pytest.raises(ErroPagBank) as erro:
        adapter.criar_pix(
            pagamento_id="pay-1",
            valor=Dinheiro("10"),
            idempotency_key="idem",
            cliente=_cliente(),
        )

    assert "401" in str(erro.value)
    assert token not in str(erro.value)


def test_erro_400_mostra_codigo_e_parametro_sem_descricao_ou_valor() -> None:
    segredo = "DADO-SENSIVEL-NAO-PODE-VAZAR"
    resposta = {
        "error_messages": [
            {
                "code": "40002",
                "description": f"campo inválido {segredo}",
                "parameter_name": "customer.tax_id",
            }
        ]
    }
    http = TransporteFake([RespostaFake(400, resposta)])
    adapter = AdapterPagBank(ConfiguracaoPagBank(token="token"), transporte=http)

    with pytest.raises(ErroPagBank) as erro:
        adapter.criar_pix(
            pagamento_id="pay-1",
            valor=Dinheiro("10"),
            idempotency_key="idem",
            cliente=_cliente(),
        )

    mensagem = str(erro.value)
    assert "400" in mensagem
    assert "code=40002" in mensagem
    assert "parameter=customer.tax_id" in mensagem
    assert segredo not in mensagem
    assert "campo inválido" not in mensagem



def _checkout_cartao(*, status: str = "ACTIVE", valor: int = 3890):
    return {
        "id": "CHEC_TESTE_SEGURANCA",
        "reference_id": "pay-cartao",
        "status": status,
        "links": [
            {
                "rel": "PAY",
                "href": "https://pagamento.pagbank.com.br/pagamento?code=teste",
            }
        ],
        "payments": (
            [{
                "id": "CHAR_CARTAO",
                "status": status,
                "amount": {"value": valor},
                "payment_method": {"type": "CREDIT_CARD"},
            }] if status != "ACTIVE" else []
        ),
    }


def test_checkout_cartao_pagbank_cria_link_sem_manipular_pan_ou_cvv() -> None:
    http = TransporteFake([RespostaFake(200, _checkout_cartao())])
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token="token-sintetico", ambiente="sandbox"),
        transporte=http,
    )
    criado = adapter.criar_checkout_cartao(
        pagamento_id="pay-cartao",
        valor=Dinheiro("38.90"),
        metodo="cartao_credito",
        idempotency_key="idem-checkout",
    )
    assert criado.checkout_id == "CHEC_TESTE_SEGURANCA"
    assert criado.status == "pendente"
    assert criado.pagamento_url.startswith("https://pagamento.pagbank.com.br/")
    chamada = http.chamadas[0]
    assert chamada["url"] == "https://sandbox.api.pagseguro.com/checkouts"
    assert chamada["headers"]["x-idempotency-key"] == "idem-checkout"
    assert chamada["json"]["customer_modifiable"] is True
    assert chamada["json"]["payment_methods"] == [{"type": "CREDIT_CARD"}]
    assert chamada["json"]["items"][0]["unit_amount"] == 3890
    assert "card" not in chamada["json"] and "cvv" not in chamada["json"]


def test_checkout_cartao_nao_considera_autorizacao_como_liquidacao() -> None:
    http = TransporteFake([
        RespostaFake(200, _checkout_cartao(status="AUTHORIZED")),
        RespostaFake(200, _checkout_cartao(status="PAID", valor=3800)),
        RespostaFake(200, _checkout_cartao(status="PAID")),
    ])
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token="token", ambiente="sandbox"), transporte=http
    )
    for esperado in ("pendente", "pendente", "pago"):
        status = adapter.consultar_checkout_cartao(
            checkout_id="CHEC_TESTE_SEGURANCA",
            pagamento_id="pay-cartao",
            valor=Dinheiro("38.90"),
            metodo="cartao_credito",
        )
        assert status.status == esperado


def test_checkout_cartao_recusa_link_pagamento_fora_do_pagbank() -> None:
    payload = _checkout_cartao()
    payload["links"][0]["href"] = "https://pagbank.com.br.atacante.example/roubo"
    http = TransporteFake([RespostaFake(200, payload)])
    adapter = AdapterPagBank(
        ConfiguracaoPagBank(token="token"), transporte=http
    )
    with pytest.raises(ErroPagBank, match="link não confiável"):
        adapter.criar_checkout_cartao(
            pagamento_id="pay-cartao",
            valor=Dinheiro("38.90"),
            metodo="cartao_credito",
            idempotency_key="idem",
        )
