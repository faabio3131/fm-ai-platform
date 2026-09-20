from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.seguranca.segredos import ReferenceSecretStore
from http_api import fmcc_core


class DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRouter:
    def __init__(self):
        self.requests = []

    def executar(self, solicitacao):
        self.requests.append(solicitacao)
        if solicitacao.capability.value == "fmcc_planning":
            return SimpleNamespace(
                conteudo={
                    "capability": "metric.query",
                    "arguments": {"metricId": "trial.starts.count"},
                }
            )
        return SimpleNamespace(conteudo={"answer": "Há 3 trials iniciados."})


def _client(monkeypatch):
    router = FakeRouter()
    monkeypatch.setenv("FM_CORE_SERVICE_TOKEN_REF", "mapping:fmcc-service")
    monkeypatch.setenv("FM_CORE_ROUTING_TENANT_ID", "core-routing-tenant")
    monkeypatch.setenv("FM_CORE_ROUTING_UNIT_ID", "core-routing-unit")
    monkeypatch.setattr(
        fmcc_core,
        "construir_ai_model_router",
        lambda **kwargs: router,
    )

    app = FastAPI()
    app.include_router(
        fmcc_core.build_fmcc_core_router(
            session_factory=lambda: DummySession(),
            secret_store=ReferenceSecretStore(
                mapping={"fmcc-service": "unit-test-token-value"}
            ),
        )
    )
    return TestClient(app), router


def _auth_headers():
    return {"Authorization": "Bearer unit-test-token-value"}


def test_shared_core_requires_service_bearer(monkeypatch):
    client, _ = _client(monkeypatch)

    response = client.post(
        "/v1/fmcc/plan",
        json={
            "question": "Quantos trials?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "allowedCapabilities": ["metric.query"],
        },
    )

    assert response.status_code == 401
    assert response.json() == {"error": "fmcc_core.service_auth_required"}


def test_shared_core_plan_contract(monkeypatch):
    client, router = _client(monkeypatch)

    response = client.post(
        "/v1/fmcc/plan",
        headers=_auth_headers(),
        json={
            "question": "Quantos trials?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "allowedCapabilities": ["metric.query"],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "capability": "metric.query",
        "arguments": {"metricId": "trial.starts.count"},
    }
    assert router.requests[0].tenant_id == "tenant-a"
    assert router.requests[0].correlation_id == "corr-a"


def test_shared_core_synthesis_contract(monkeypatch):
    client, router = _client(monkeypatch)
    evidence = [
        {
            "kind": "metric",
            "ref": "trial.starts.count",
            "sourceAuthority": "trial-source",
        }
    ]

    response = client.post(
        "/v1/fmcc/synthesize",
        headers=_auth_headers(),
        json={
            "question": "Quantos trials?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "facts": [
                {
                    "metricId": "trial.starts.count",
                    "value": "3",
                    "unit": "count",
                }
            ],
            "evidence": evidence,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Há 3 trials iniciados.",
        "evidence": evidence,
        "factualStatus": "grounded",
    }
    assert router.requests[-1].tenant_id == "tenant-a"


def test_shared_core_fails_closed_without_routing_scope(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.delenv("FM_CORE_ROUTING_TENANT_ID")

    response = client.post(
        "/v1/fmcc/plan",
        headers=_auth_headers(),
        json={
            "question": "Quantos trials?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "allowedCapabilities": ["metric.query"],
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": "fmcc_core.cognitive_runtime_unavailable"
    }


def test_shared_core_http_forwards_operational_context(monkeypatch):
    client, router = _client(monkeypatch)
    context = [
        {
            "question": "Quanto faturamos ontem?",
            "answer": "R$ 100,00",
            "factualStatus": "grounded",
            "evidenceRefs": ["billing.gross_billed"],
        }
    ]

    response = client.post(
        "/v1/fmcc/plan",
        headers=_auth_headers(),
        json={
            "question": "E hoje?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "allowedCapabilities": ["metric.query", "metrics.query_many"],
            "operationalContext": context,
        },
    )

    assert response.status_code == 200
    assert router.requests[-1].conteudo["operational_context"] == context
