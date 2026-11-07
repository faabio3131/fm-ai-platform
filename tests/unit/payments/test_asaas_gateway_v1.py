"""Contrato Asaas v3 sem HTTP externo e sem movimentação financeira."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.asaas import (
    AdapterAsaas,
    ConfiguracaoAsaas,
    ErroAsaas,
    PagadorAsaas,
)


def _valor() -> Dinheiro:
    return Dinheiro(Decimal("30.00"))


def _adapter(handler, token: str | None = "w" * 40) -> AdapterAsaas:
    return AdapterAsaas(
        ConfiguracaoAsaas(api_key="segredo-falso", webhook_token=token),
        transporte=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _cobranca(status="PENDING", reference="kordena:tenantA:unitA:pay1", value=30.0, **extra):
    return dict(id="pay_A123", externalReference=reference, status=status,
                billingType="PIX", value=value, **extra)


def test_asaas_pix_e2e_cliente_cobranca_qr_consulta_pago_sem_duplicar():
    calls: list[tuple[str, str]] = []
    state = {"customer": False, "payment": False, "status": "PENDING"}

    def api(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api-sandbox.asaas.com"
        assert request.headers["access_token"] == "segredo-falso"
        assert request.headers["User-Agent"] == "Kordena/1.0"
        calls.append((request.method, request.url.path))
        path = request.url.path
        if path == "/v3/customers" and request.method == "GET":
            return httpx.Response(200, json={"data": [
                {"id": "cus_A", "externalReference": "kordena:tenantA:unitA:client1",
                 "cpfCnpj": "12345678909"}] if state["customer"] else []})
        if path == "/v3/customers" and request.method == "POST":
            state["customer"] = True
            return httpx.Response(200, json={
                "id": "cus_A", "externalReference": "kordena:tenantA:unitA:client1",
                "cpfCnpj": "12345678909",
            })
        if path == "/v3/payments" and request.method == "GET":
            return httpx.Response(200, json={"data": [
                _cobranca(state["status"])] if state["payment"] else []})
        if path == "/v3/payments" and request.method == "POST":
            state["payment"] = True
            return httpx.Response(200, json=_cobranca())
        if path == "/v3/payments/pay_A123/pixQrCode":
            return httpx.Response(200, json={
                "payload": "000201chave-pix-teste", "encodedImage": "base64qa",
            })
        if path == "/v3/payments/pay_A123":
            return httpx.Response(200, json=_cobranca(state["status"]))
        raise AssertionError(f"Unexpected request {request.method} {path}")

    adapter = _adapter(api)
    payer = PagadorAsaas("Cliente QA", "qa@example.com", "123.456.789-09")
    customer = adapter.obter_ou_criar_cliente(payer, reference="kordena:tenantA:unitA:client1")
    customer_2 = adapter.obter_ou_criar_cliente(payer, reference="kordena:tenantA:unitA:client1")
    assert customer == customer_2 == "cus_A"
    charge = adapter.criar_cobranca(
        reference="kordena:tenantA:unitA:pay1", customer_id=customer,
        metodo="PIX", valor=_valor(), vencimento=date(2026, 11, 9),
    )
    again = adapter.criar_cobranca(
        reference="kordena:tenantA:unitA:pay1", customer_id=customer,
        metodo="PIX", valor=_valor(), vencimento=date(2026, 11, 9),
    )
    assert charge.id_externo == again.id_externo == "pay_A123"
    assert charge.pix_copia_cola == "000201chave-pix-teste"
    assert [c for c in calls if c == ("POST", "/v3/customers")] == [("POST", "/v3/customers")]
    assert [c for c in calls if c == ("POST", "/v3/payments")] == [("POST", "/v3/payments")]
    assert charge.como_cobranca().status == "pendente"
    state["status"] = "RECEIVED"
    confirmed = adapter.consultar_cobranca(
        id_externo="pay_A123", reference="kordena:tenantA:unitA:pay1",
        metodo="PIX", valor=_valor(),
    )
    assert confirmed.status == "pago"
    assert confirmed.valor == _valor()


@pytest.mark.parametrize("wrong", [
    {"status": "RECEIVED", "value": 29.99},
    {"status": "RECEIVED", "externalReference": "outro-tenant"},
    {"status": "RECEIVED", "billingType": "CREDIT_CARD"},
    {"status": "NEVER_SEEN"},
])
def test_asaas_consulta_falha_fechada(wrong: dict[str, Any]):
    data = _cobranca()
    data.update(wrong)
    adapter = _adapter(lambda _: httpx.Response(200, json=data))
    with pytest.raises(ErroAsaas):
        adapter.consultar_cobranca(
            id_externo="pay_A123", reference="kordena:tenantA:unitA:pay1",
            metodo="PIX", valor=_valor(),
        )


def test_asaas_autorizado_nao_liquida():
    adapter = _adapter(lambda _: httpx.Response(200, json=_cobranca("AUTHORIZED")))
    result = adapter.consultar_cobranca(
        id_externo="pay_A123", reference="kordena:tenantA:unitA:pay1",
        metodo="PIX", valor=_valor(),
    )
    assert result.status == "pendente"


def test_asaas_webhook_autenticado_idempotency_id_e_status():
    adapter = _adapter(lambda _: httpx.Response(500))
    payload = {
        "id": "evt_123", "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_A123", "externalReference": "kordena:tenantA:unitA:pay1",
            "value": 30, "status": "RECEIVED",
        },
    }
    with pytest.raises(ErroAsaas, match="asaas_webhook_nao_autenticado"):
        adapter.autenticar_webhook(recebido="invalido", payload=payload)
    parsed = adapter.autenticar_webhook(recebido="w" * 40, payload=payload)
    assert parsed.id_evento == "evt_123"
    assert parsed.referencia == "kordena:tenantA:unitA:pay1"
    assert parsed.valor == _valor()
    assert parsed.evento == "PAYMENT_RECEIVED"


def test_asaas_recebimento_de_url_hostil_e_recusado():
    data = _cobranca()
    data["invoiceUrl"] = "https://www.asaas.com.attacker.invalid/checkout"
    adapter = _adapter(lambda _: httpx.Response(200, json=data))
    with pytest.raises(ErroAsaas, match="asaas_url_nao_confiavel"):
        adapter.consultar_cobranca(
            id_externo="pay_A123", reference="kordena:tenantA:unitA:pay1",
            metodo="PIX", valor=_valor(),
        )


def test_asaas_refund_nao_significa_liquidacao_devolucao():
    seen = []
    def api(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json={"status": "PROCESSING"})
    adapter = _adapter(api)
    assert adapter.solicitar_estorno(id_externo="pay_A123", valor=_valor()) == "PROCESSING"
    assert seen[0].url.path == "/v3/payments/pay_A123/refund"
    with pytest.raises(ErroAsaas):
        adapter.solicitar_estorno(id_externo="../../admin")


def test_asaas_ambiguidade_lista_nao_faz_post():
    seen = []
    def api(request: httpx.Request):
        seen.append(request.method)
        return httpx.Response(200, json={"data": [
            {"id": "cus_A", "externalReference": "cliente1"},
            {"id": "cus_B", "externalReference": "cliente1"},
        ]})
    adapter = _adapter(api)
    with pytest.raises(ErroAsaas, match="asaas_referencia_ambigua"):
        adapter.obter_ou_criar_cliente(
            PagadorAsaas("Teste", "qa@example.com", "12345678909"), reference="cliente1",
        )
    assert seen == ["GET"]
