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

SESSION_SECRET = "auth-http-contract-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Auth-HTTP-123"
EMAIL = "operador-auth@example.com"
USUARIO_ID = "usuario-auth-http-01"
TENANT = "tenant-auth-http"
UNIDADE_A = "unidade-auth-a"
UNIDADE_B = "unidade-auth-b"
UNIDADE_PROIBIDA = "unidade-auth-proibida"


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
            usuario_id=USUARIO_ID,
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        session.commit()

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite://",
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
    )
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
    )
    return TestClient(app)


def _login(client: TestClient):
    return client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": SENHA},
    )


def test_login_valido_emite_cookie_de_sessao(monkeypatch) -> None:
    client = _infra(monkeypatch)

    response = _login(client)

    assert response.status_code == 200
    assert response.json() == {
        "usuario_id": USUARIO_ID,
        "nome": None,
        "email": EMAIL,
        "tenant_id": TENANT,
        "unidade_ativa_id": UNIDADE_A,
        "papeis": ["gerente"],
    }
    set_cookie = response.headers["set-cookie"].lower()
    assert "fm_ai_session=" in set_cookie
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie


def test_login_invalido_retorna_401(monkeypatch) -> None:
    client = _infra(monkeypatch)

    response = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": "senha-incorreta-123"},
    )

    assert response.status_code == 401
    assert response.json() == {"erro": "seguranca.credenciais_invalidas"}


def test_me_exige_sessao_e_aceita_cookie_ou_bearer(monkeypatch) -> None:
    client = _infra(monkeypatch)
    sem_sessao = client.get("/v1/auth/me")
    assert sem_sessao.status_code == 401

    login = _login(client)
    assert login.status_code == 200
    token = client.cookies.get("fm_ai_session")
    assert token

    por_cookie = client.get("/v1/auth/me")
    assert por_cookie.status_code == 200
    body = por_cookie.json()
    assert body["usuario_id"] == USUARIO_ID
    assert body["tenant_id"] == TENANT
    assert body["unidade_ativa_id"] == UNIDADE_A
    assert body["papeis"] == ["gerente"]
    assert "permissoes" in body
    assert "pdv.operar" in body["permissoes"]

    bearer_client = TestClient(client.app)
    por_bearer = bearer_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert por_bearer.status_code == 200
    assert por_bearer.json()["usuario_id"] == USUARIO_ID


def test_lista_unidades_autorizadas(monkeypatch) -> None:
    client = _infra(monkeypatch)
    assert _login(client).status_code == 200

    response = client.get("/v1/auth/unidades")

    assert response.status_code == 200
    assert response.json() == [
        {"id": UNIDADE_A, "codigo": None, "nome": None},
        {"id": UNIDADE_B, "codigo": None, "nome": None},
    ]


def test_selecao_de_unidade_permitida_e_rejeicao_da_nao_autorizada(monkeypatch) -> None:
    client = _infra(monkeypatch)
    assert _login(client).status_code == 200

    permitida = client.post(
        "/v1/auth/select-unit",
        json={"unidade_id": UNIDADE_B},
    )
    assert permitida.status_code == 200
    assert permitida.json() == {"unidade_ativa_id": UNIDADE_B}
    assert client.get("/v1/auth/me").json()["unidade_ativa_id"] == UNIDADE_B

    proibida = client.post(
        "/v1/auth/select-unit",
        json={"unidade_id": UNIDADE_PROIBIDA},
    )
    assert proibida.status_code == 403
    assert proibida.json() == {"erro": "seguranca.recurso_indisponivel"}
    assert client.get("/v1/auth/me").json()["unidade_ativa_id"] == UNIDADE_B


def test_logout_expira_cookie_e_invalida_sessao(monkeypatch) -> None:
    client = _infra(monkeypatch)
    login = _login(client)
    assert login.status_code == 200
    token = client.cookies.get("fm_ai_session")
    assert token

    response = client.post("/v1/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    set_cookie = response.headers["set-cookie"].lower()
    assert "fm_ai_session=" in set_cookie
    assert "max-age=0" in set_cookie
    assert client.get("/v1/auth/me").status_code == 401

    bearer_client = TestClient(client.app)
    revogada = bearer_client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert revogada.status_code == 401
