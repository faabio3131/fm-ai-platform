from __future__ import annotations

from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.segredos import ReferenceSecretStore
from http_api.frontend_app import build_frontend_http_app
from migrations.runner import run_migrations

KEY = "obShALmcxtf1vGcUP3xIs6mVnxov9bHzsOSQ_r9SXI4="
PASSWORD = "Senha-Segura-KCA06-123"


@dataclass
class FakeDispatcher:
    sent: list[tuple[str, str, str]] = field(default_factory=list)

    def send_verification(self, *, signup_id: str, email: str, token: str) -> None:
        self.sent.append((signup_id, email, token))


def _client(*, enabled: bool):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    dispatcher = FakeDispatcher()
    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id="bootstrap",
            unidade_id="bootstrap",
        ),
        engine=engine,
        session_factory=factory,
        secret_store=ReferenceSecretStore(mapping={"signup": KEY}),
        public_signup_enabled=enabled,
        signup_verification_dispatcher=dispatcher,
        signup_credential_secret_reference="mapping:signup",
    )
    return TestClient(app), dispatcher


def _payload(email: str = "signup-http@example.com"):
    return {
        "owner_name": "Responsável",
        "email": email,
        "password": PASSWORD,
        "phone": "+5511999999999",
        "establishment_name": "Restaurante HTTP",
        "segment": "restaurante",
        "terms_accepted": True,
        "consents": {"marketing": False},
    }


def test_signup_publico_fica_desativado_por_padrao() -> None:
    client, _ = _client(enabled=False)
    assert client.post("/v1/public/signup", json=_payload()).status_code == 404


def test_signup_verifica_email_e_provisiona() -> None:
    client, dispatcher = _client(enabled=True)
    response = client.post("/v1/public/signup", json=_payload())
    assert response.status_code == 202
    signup_id = response.json()["signup_id"]
    assert len(dispatcher.sent) == 1
    sent_id, sent_email, token = dispatcher.sent[0]
    assert sent_id == signup_id
    assert sent_email == "signup-http@example.com"

    verified = client.post(
        f"/v1/public/signup/{signup_id}/verify-email",
        json={"token": token},
    )
    assert verified.status_code == 200
    assert verified.json()["ready"] is True

    status_response = client.get(f"/v1/public/signup/{signup_id}/status")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready"

    replay = client.post(
        f"/v1/public/signup/{signup_id}/verify-email",
        json={"token": token},
    )
    assert replay.status_code == 400


def test_payload_nao_pode_injetar_autoridades() -> None:
    client, _ = _client(enabled=True)
    payload = _payload("forged@example.com")
    payload["tenant_id"] = "tenant-forjado"
    payload["plan_code"] = "KORDENA_PLAN_D"
    payload["entitlement"] = "FULL"
    assert client.post("/v1/public/signup", json=payload).status_code == 422


def test_email_duplicado_nao_e_enumerado_na_resposta() -> None:
    client, _ = _client(enabled=True)
    first = client.post("/v1/public/signup", json=_payload("same@example.com"))
    second = client.post("/v1/public/signup", json=_payload("same@example.com"))
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["accepted"] is True
    assert second.json()["accepted"] is True
    assert first.json()["message"] == second.json()["message"]


def test_rate_limit_bloqueia_excesso_por_origem() -> None:
    client, _ = _client(enabled=True)
    statuses = [
        client.post(
            "/v1/public/signup",
            json=_payload(f"rate{i}@example.com"),
        ).status_code
        for i in range(6)
    ]
    assert statuses[:5] == [202] * 5
    assert statuses[5] == 429
