from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "kca02-membership-http-secret-0123456789-abcdef"
PASSWORD = "Senha-KCA02-Membership-123"
EMAIL = "multi-http@example.com"
TENANT_A = "tenant-kca02-a"
TENANT_B = "tenant-kca02-b"
UNIT_A = "unit-kca02-a"
UNIT_B = "unit-kca02-b"


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
        repo = RepositorioIdentidadesSQLAlchemy(session)
        primeira = repo.criar_usuario(
            email=EMAIL,
            password=PASSWORD,
            tenant_id=TENANT_A,
            unidade_padrao_id=UNIT_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIT_A,),
        )
        segunda = repo.criar_membership_existente(
            identity_user_id=primeira.global_identity_id,
            tenant_id=TENANT_B,
            unidade_padrao_id=UNIT_B,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIT_B,),
        )
        outro = repo.criar_usuario(
            email="outro-kca02@example.com",
            password="Senha-Outro-KCA02-123",
            tenant_id="tenant-outro",
            unidade_padrao_id="unit-outro",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("unit-outro",),
        )
        session.commit()

    app = build_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT_A,
            unidade_id=UNIT_A,
        ),
        engine=engine,
        session_factory=factory,
    )
    return (
        TestClient(app),
        primeira.membership_subject_id,
        segunda.membership_subject_id,
        outro.membership_subject_id,
    )


def test_login_lista_e_troca_membership_sem_nova_credencial(monkeypatch) -> None:
    client, membership_a, membership_b, _ = _infra(monkeypatch)

    login = client.post("/v1/auth/login", json={"email": EMAIL, "senha": PASSWORD})
    assert login.status_code == 200
    assert login.json()["tenant_id"] == TENANT_A

    memberships = client.get("/v1/auth/memberships")
    assert memberships.status_code == 200
    assert {item["tenant_id"] for item in memberships.json()} == {TENANT_A, TENANT_B}
    atual = next(item for item in memberships.json() if item["atual"])
    assert atual["membership_id"] == membership_a

    troca = client.post(
        "/v1/auth/select-membership",
        json={"membership_id": membership_b},
    )
    assert troca.status_code == 200
    assert troca.json() == {
        "membership_id": membership_b,
        "tenant_id": TENANT_B,
        "unidade_ativa_id": UNIT_B,
    }

    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["tenant_id"] == TENANT_B
    assert me.json()["unidade_ativa_id"] == UNIT_B


def test_troca_de_membership_revoga_step_up(monkeypatch) -> None:
    client, _, membership_b, _ = _infra(monkeypatch)
    assert client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": PASSWORD},
    ).status_code == 200
    assert client.post(
        "/v1/auth/admin-step-up",
        json={"senha": PASSWORD},
    ).status_code == 200
    assert client.get("/v1/auth/admin-status").json()["elevado"] is True

    troca = client.post(
        "/v1/auth/select-membership",
        json={"membership_id": membership_b},
    )
    assert troca.status_code == 200
    assert client.get("/v1/auth/admin-status").json()["elevado"] is False


def test_nao_seleciona_membership_de_outra_identidade(monkeypatch) -> None:
    client, _, _, membership_outro = _infra(monkeypatch)
    assert client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": PASSWORD},
    ).status_code == 200

    response = client.post(
        "/v1/auth/select-membership",
        json={"membership_id": membership_outro},
    )
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.recurso_indisponivel"}


def test_membership_inexistente_falha_fechado(monkeypatch) -> None:
    client, _, _, _ = _infra(monkeypatch)
    assert client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": PASSWORD},
    ).status_code == 200

    response = client.post(
        "/v1/auth/select-membership",
        json={"membership_id": "membership-inexistente"},
    )
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.recurso_indisponivel"}


def test_old_membership_token_cannot_be_replayed_after_switch(monkeypatch) -> None:
    client, _, membership_b, _ = _infra(monkeypatch)
    assert client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": PASSWORD},
    ).status_code == 200
    old_token = client.cookies.get("fm_ai_session")
    assert old_token

    switched = client.post(
        "/v1/auth/select-membership",
        json={"membership_id": membership_b},
    )
    assert switched.status_code == 200
    assert switched.json()["tenant_id"] == TENANT_B

    replay_client = TestClient(client.app)
    replay = replay_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert replay.status_code == 401
    assert client.get("/v1/auth/me").json()["tenant_id"] == TENANT_B
