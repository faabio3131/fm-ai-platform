from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.segredos import ReferenceSecretStore
from http_api.fmcc_core_app import build_fmcc_core_app


def _settings() -> RuntimeSettings:
    return RuntimeSettings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite:///:memory:",
        tenant_id="core-runtime-test",
        unidade_id="core-runtime-unit",
    ).validate()


def _app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    return build_fmcc_core_app(
        settings=_settings(),
        engine=engine,
        session_factory=factory,
        secret_store=ReferenceSecretStore(
            mapping={"service-token": "unit-test-token-value"}
        ),
    )


def test_dedicated_app_exposes_health_and_only_shared_core_surface(monkeypatch):
    monkeypatch.setenv(
        "FM_CORE_SERVICE_TOKEN_REF",
        "mapping:service-token",
    )
    app = _app()
    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["service"] == "fm-cognitive-core"
    assert health.json()["ok"] is True

    # Dedicated runtime must not expose Kordena operational/auth surfaces.
    assert client.get("/v1/auth/me").status_code == 404
    assert client.post("/v1/core/tools", json={}).status_code == 404

    # Shared-Core contract is mounted and remains service-authenticated.
    unauthenticated = client.post(
        "/v1/fmcc/plan",
        json={
            "question": "Quantos trials?",
            "tenantId": "tenant-a",
            "userId": "user-a",
            "correlationId": "corr-a",
            "allowedCapabilities": ["metric.query"],
        },
    )
    assert unauthenticated.status_code == 401


def test_commercial_runtime_hides_openapi():
    settings = RuntimeSettings(
        environment=RuntimeEnvironment.STAGING,
        database_url="postgresql://example.invalid/fmcore",
        tenant_id="routing-tenant",
        unidade_id="routing-unit",
    ).validate()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    # We inject the engine/session factory so this contract test does not attempt
    # an external database connection; only the commercial HTTP surface matters.
    app = build_fmcc_core_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        secret_store=ReferenceSecretStore(mapping={}),
    )
    client = TestClient(app)

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
