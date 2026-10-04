from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.password_recovery_orm import PasswordRecoveryTokenORM
from migrations.runner import run_migrations

SESSION_SECRET = "password-recovery-http-secret-0123456789-abcdef"
EMAIL = "owner-recovery@example.com"
PASSWORD = "Senha-Atual-Segura-123"
NEW_PASSWORD = "Senha-Nova-Segura-456"
TENANT = "tenant-recovery"
UNIT = "unit-recovery"


@dataclass
class FakePasswordRecoveryDispatcher:
    resets: list[tuple[str, str]] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)

    def send_password_reset(self, *, email: str, token: str) -> None:
        self.resets.append((email, token))

    def send_password_changed(self, *, email: str) -> None:
        self.changed.append(email)


def _infra(monkeypatch):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email=EMAIL,
            password=PASSWORD,
            tenant_id=TENANT,
            unidade_padrao_id=UNIT,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIT,),
            acesso_admin_sensivel=True,
        )
        session.commit()

    dispatcher = FakePasswordRecoveryDispatcher()
    app = build_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIT,
        ),
        engine=engine,
        session_factory=factory,
        password_recovery_dispatcher=dispatcher,
    )
    return TestClient(app), factory, dispatcher


def _login(client: TestClient, password: str = PASSWORD):
    return client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": password},
    )


def test_forgot_password_nao_enumera_conta_e_token_nao_e_persistido_em_claro(monkeypatch) -> None:
    client, factory, dispatcher = _infra(monkeypatch)

    known = client.post("/v1/auth/forgot-password", json={"email": EMAIL})
    unknown = client.post(
        "/v1/auth/forgot-password",
        json={"email": "nao-existe@example.com"},
    )

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(dispatcher.resets) == 1
    recipient, token = dispatcher.resets[0]
    assert recipient == EMAIL
    with factory() as session:
        row = session.scalar(select(PasswordRecoveryTokenORM))
        assert row is not None
        assert row.token_sha256 == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert token not in row.token_sha256


def test_reset_password_e_uso_unico_revogam_sessoes(monkeypatch) -> None:
    client, _, dispatcher = _infra(monkeypatch)
    assert _login(client).status_code == 200
    assert client.get("/v1/auth/me").status_code == 200

    assert client.post("/v1/auth/forgot-password", json={"email": EMAIL}).status_code == 202
    token = dispatcher.resets[-1][1]

    reset = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "nova_senha": NEW_PASSWORD},
    )
    assert reset.status_code == 200
    assert reset.json() == {"ok": True}
    assert dispatcher.changed == [EMAIL]

    assert client.get("/v1/auth/me").status_code == 401
    assert _login(client).status_code == 401
    assert _login(client, NEW_PASSWORD).status_code == 200

    replay = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "nova_senha": "Outra-Senha-Segura-789"},
    )
    assert replay.status_code == 400
    assert replay.json() == {"erro": "password_recovery_token_invalid"}


def test_reset_rejeita_senha_fraca_sem_consumir_token(monkeypatch) -> None:
    client, _, dispatcher = _infra(monkeypatch)
    client.post("/v1/auth/forgot-password", json={"email": EMAIL})
    token = dispatcher.resets[-1][1]

    weak = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "nova_senha": "curta123"},
    )
    assert weak.status_code == 422
    assert _login(client).status_code == 200


def test_change_password_exige_senha_atual_e_forca_reautenticacao(monkeypatch) -> None:
    client, _, dispatcher = _infra(monkeypatch)
    assert _login(client).status_code == 200

    invalid = client.post(
        "/v1/auth/change-password",
        json={"senha_atual": "senha-errada", "nova_senha": NEW_PASSWORD},
    )
    assert invalid.status_code == 401

    changed = client.post(
        "/v1/auth/change-password",
        json={"senha_atual": PASSWORD, "nova_senha": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    assert changed.json() == {"ok": True, "reauthentication_required": True}
    assert client.get("/v1/auth/me").status_code == 401
    assert dispatcher.changed == [EMAIL]
    assert _login(client, NEW_PASSWORD).status_code == 200


def test_rate_limit_publico_permanece_resposta_generica(monkeypatch) -> None:
    client, _, dispatcher = _infra(monkeypatch)

    responses = [
        client.post("/v1/auth/forgot-password", json={"email": EMAIL})
        for _ in range(7)
    ]
    assert all(response.status_code == 202 for response in responses)
    assert len(dispatcher.resets) <= 5
