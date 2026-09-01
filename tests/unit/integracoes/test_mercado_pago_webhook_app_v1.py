from __future__ import annotations

from contextlib import AbstractContextManager

from fastapi.testclient import TestClient

from core.integracoes.provedores import EventoWebhookProvedor
from infra.integracoes import mercado_pago_webhook_app as modulo


class _Sessao(AbstractContextManager):
    def rollback(self) -> None:
        pass

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _SessionFactory:
    def __call__(self) -> _Sessao:
        return _Sessao()


class _Adapter:
    def __init__(self) -> None:
        self.consultas = 0

    def normalizar_webhook(self, **kwargs) -> EventoWebhookProvedor:
        return EventoWebhookProvedor(
            provedor="mercado_pago",
            evento_id="evt-123",
            recurso_id="123456",
            tipo="order.processed",
            assinatura_validada=True,
            idempotency_key="mercado_pago:evt-123:123456:order.processed",
        )

    def consultar_pagamento(self, pagamento_id: str):
        self.consultas += 1
        raise AssertionError("Order sem vinculo local nao deve consultar API externa")


def test_webhook_assinado_sem_vinculo_local_retorna_200_sem_consultar_order(monkeypatch) -> None:
    adapter = _Adapter()
    monkeypatch.setattr(modulo, "_adapter_pre_homologacao", lambda *args, **kwargs: adapter)
    monkeypatch.setattr(modulo, "_vinculo_por_order", lambda *args, **kwargs: None)

    app = modulo.create_app(
        session_factory=_SessionFactory(),
        tenant_id="tenant-local",
        unidade_id="unidade-local",
    )
    client = TestClient(app)

    response = client.post(
        "/webhooks/mercado-pago?data.id=123456&type=order",
        headers={
            "x-request-id": "req-123",
            "x-signature": "ts=1,v1=assinatura-validada-pelo-adapter",
        },
        json={
            "action": "order.processed",
            "type": "order",
            "data": {"id": "123456"},
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "resource": "order",
        "reconciled": False,
    }
    assert adapter.consultas == 0
