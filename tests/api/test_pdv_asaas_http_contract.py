"""PDV Asaas end-to-end: authenticated HTTP => ledger => UoW => stock/sale.

PSP transport is a stateful HTTPX fake, not a fake internal payment ledger.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from application import pdv_asaas
from core.pagamentos.asaas import AdapterAsaas, ConfiguracaoAsaas
from core.pagamentos.modelos_orm import PagamentoORM, VendaFinanceiraORM
from core.pedidos.modelos_orm import PedidoORM
from tests.api.test_pdv_http_contract import _headers, _infra, _payload


@dataclass
class PSPFixture:
    status: str = "PENDING"
    customer_creates: int = 0
    charge_creates: int = 0
    consultations: int = 0

    def transport(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api-sandbox.asaas.com"
        assert request.headers["access_token"] == "QA-TOKEN-FAKE"
        path = request.url.path
        if path == "/v3/customers":
            if request.method == "GET":
                return httpx.Response(200, json={"data": (
                    [{"id": "cus_QA", "externalReference": str(request.url.params["externalReference"])}]
                    if self.customer_creates else []
                )})
            self.customer_creates += 1
            payload = __import__("json").loads(request.content)
            return httpx.Response(200, json={
                "id": "cus_QA", "externalReference": payload["externalReference"],
            })
        if path == "/v3/payments":
            if request.method == "GET":
                return httpx.Response(200, json={
                    "data": [self._charge(str(request.url.params["externalReference"]))]
                    if self.charge_creates else []
                })
            self.charge_creates += 1
            payload = __import__("json").loads(request.content)
            self.reference = payload["externalReference"]
            self.method = payload["billingType"]
            return httpx.Response(200, json=self._charge(self.reference))
        if path == "/v3/payments/pay_QA/pixQrCode":
            return httpx.Response(200, json={
                "payload": "000201PIX-TESTE", "encodedImage": "dGVzdGU=",
            })
        if path == "/v3/payments/pay_QA":
            self.consultations += 1
            return httpx.Response(200, json=self._charge(self.reference))
        raise AssertionError(f"PSP route not covered: {path}")

    def _charge(self, ref: str) -> dict:
        return {
            "id": "pay_QA", "externalReference": ref,
            "billingType": getattr(self, "method", "PIX"),
            "value": 30,
            "status": self.status,
            "invoiceUrl": "https://www.asaas.com/i/qa123",
        }


class Factory:
    def __init__(self, psp: PSPFixture):
        self.psp = psp
        self.requested: list[tuple[str, str, str]] = []

    def construir(self, *, session, tenant_id, unidade_id, servico):
        self.requested.append((tenant_id, unidade_id, servico))
        return AdapterAsaas(
            ConfiguracaoAsaas(
                api_key="QA-TOKEN-FAKE", webhook_token="w" * 40,
            ),
            transporte=httpx.Client(transport=httpx.MockTransport(self.psp.transport)),
        )


def _payer() -> dict:
    return {"nome": "Pessoa QA", "email": "qa@example.com", "documento": "12345678909"}


def _checkout(client, method: str = "pix", key: str = "e44f2e8f-863d-4249-aee4-fc5127ca8c9d"):
    result = client.post(
        "/v1/pdv/checkout", headers=_headers(key),
        json={**_payload(), "metodo_pagamento": method, "provedor_pagamento": "asaas"},
    )
    assert result.status_code == 201, result.text
    assert result.json()["pagamento"]["provedor"] == "asaas"
    return result.json()["pagamento"]["id"]


@pytest.mark.parametrize("method,service", [
    ("pix", "pagamentos.pix"), ("cartao_credito", "pagamentos.cartao"),
])
def test_asaas_pdv_fluo_cobranca_pendente_replay_liquidacao_uma_vez(
    monkeypatch, method: str, service: str,
):
    engine, _, client = _infra()
    psp = PSPFixture()
    factory = Factory(psp)
    monkeypatch.setattr(pdv_asaas, "AsaasAdapterFactory", lambda: factory)
    payment = _checkout(client, method)
    base = f"/v1/pdv/pagamentos/{payment}"
    started = client.post(base + "/iniciar-asaas", json=_payer(), headers=_headers())
    assert started.status_code == 201, started.text
    assert started.json()["order_id"] == "pay_QA"
    if method == "pix":
        assert started.json()["pix_copia_cola"] == "000201PIX-TESTE"
    else:
        assert started.json()["pagamento_url"].startswith("https://www.asaas.com/")
    replay = client.post(base + "/iniciar-asaas", json=_payer(), headers=_headers())
    assert replay.status_code == 200, replay.text
    assert replay.json()["idempotente"] is True
    assert psp.charge_creates == psp.customer_creates == 1
    pending = client.post(base + "/verificar-asaas", headers=_headers())
    assert pending.status_code == 200, pending.text
    assert pending.json()["status_pagamento"] != "pago"
    psp.status = "RECEIVED"
    success = client.post(base + "/verificar-asaas", headers=_headers())
    assert success.status_code == 200, success.text
    assert success.json()["status_pagamento"] == "pago"
    repeated = client.post(base + "/verificar-asaas", headers=_headers())
    assert repeated.status_code == 200
    assert repeated.json()["status_pagamento"] == "pago"
    assert all(s[2] == service for s in factory.requested)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1


def test_webhook_asaas_rejeita_assinatura_sem_liquidar(monkeypatch):
    engine, _, client = _infra()
    psp = PSPFixture()
    factory = Factory(psp)
    monkeypatch.setattr(pdv_asaas, "AsaasAdapterFactory", lambda: factory)
    payment = _checkout(client)
    created = client.post(
        f"/v1/pdv/pagamentos/{payment}/iniciar-asaas",
        json=_payer(), headers=_headers(),
    )
    assert created.status_code == 201, created.text
    event = {
        "id": "evt_QA", "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_QA", "externalReference": psp.reference,
            "value": 30, "status": "RECEIVED",
        },
    }
    forged = client.post(
        "/webhooks/asaas",
        headers={"asaas-access-token": "spoof"},
        json=event,
    )
    assert forged.status_code == 401
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
    # The body claims RECEIVED; authenticated PSP GET is still pending.
    pending = client.post(
        "/webhooks/asaas", headers={"asaas-access-token": "w" * 40},
        json=event,
    )
    assert pending.status_code == 200, pending.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 0
    psp.status = "RECEIVED"
    settled = client.post(
        "/webhooks/asaas", headers={"asaas-access-token": "w" * 40},
        json=event,
    )
    assert settled.status_code == 200, settled.text
    second = client.post(
        "/webhooks/asaas", headers={"asaas-access-token": "w" * 40},
        json=event,
    )
    assert second.status_code == 200, second.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendaFinanceiraORM)) == 1


def test_asaas_sem_credencial_nao_inicia_nem_confirma():
    engine, _, client = _infra()
    payment = _checkout(client)
    response = client.post(
        f"/v1/pdv/pagamentos/{payment}/iniciar-asaas",
        headers=_headers(), json=_payer(),
    )
    assert response.status_code == 503, response.text
    with Session(engine) as session:
        row = session.scalar(select(PagamentoORM).where(PagamentoORM.id == payment))
        assert row is not None
        assert row.status != "pago"


@pytest.mark.parametrize("method", ["dinheiro", "cartao_debito"])
def test_asaas_nao_autoriza_metodo_incompativel(method: str):
    _, _, client = _infra()
    response = client.post(
        "/v1/pdv/checkout", headers=_headers(),
        json={**_payload(), "metodo_pagamento": method, "provedor_pagamento": "asaas"},
    )
    assert response.status_code == 400, response.text


def test_asaas_provedor_nao_pode_ser_trocado_por_replay_de_mesma_venda():
    engine, _, client = _infra()
    key = "01a56587-44b6-49ee-b1de-13f038e12430"
    first = client.post(
        "/v1/pdv/checkout", headers=_headers(key),
        json={**_payload(), "metodo_pagamento": "pix", "provedor_pagamento": "asaas"},
    )
    assert first.status_code == 201, first.text
    replay = client.post(
        "/v1/pdv/checkout", headers=_headers(key),
        json={**_payload(), "metodo_pagamento": "pix", "provedor_pagamento": "pagbank"},
    )
    assert replay.status_code == 409, replay.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 1


def test_asaas_spoof_cross_unit_nao_permite_visualizar_cobranca(monkeypatch):
    _, _, client = _infra()
    factory = Factory(PSPFixture())
    monkeypatch.setattr(pdv_asaas, "AsaasAdapterFactory", lambda: factory)
    pagamento = _checkout(client)
    headers = _headers()
    headers["X-Unit-ID"] = "unidade-nao-permitida"
    response = client.post(
        f"/v1/pdv/pagamentos/{pagamento}/iniciar-asaas",
        headers=headers, json=_payer(),
    )
    assert response.status_code in (401, 403), response.text
    assert factory.requested == []


def test_asaas_estorno_confirmado_por_get_e_idempotente(monkeypatch):
    engine, _, client = _infra()
    psp = PSPFixture()
    factory = Factory(psp)
    monkeypatch.setattr(pdv_asaas, "AsaasAdapterFactory", lambda: factory)
    payment = _checkout(client)
    url = f"/v1/pdv/pagamentos/{payment}"
    started = client.post(url + "/iniciar-asaas", headers=_headers(), json=_payer())
    assert started.status_code == 201, started.text
    psp.status = "RECEIVED"
    assert client.post(url + "/verificar-asaas", headers=_headers()).json()["status_pagamento"] == "pago"
    psp.status = "REFUNDED"
    first = client.post(url + "/verificar-asaas", headers=_headers())
    assert first.status_code == 200, first.text
    assert first.json()["status_pagamento"] == "estornado"
    replay = client.post(url + "/verificar-asaas", headers=_headers())
    assert replay.status_code == 200, replay.text
    assert replay.json()["status_pagamento"] == "estornado"
    with Session(engine) as session:
        row = session.scalar(select(PagamentoORM).where(PagamentoORM.id == payment))
        assert row is not None
        assert Decimal(str(row.valor_estornado)) == Decimal("30.00")
