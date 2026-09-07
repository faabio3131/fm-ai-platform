from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "admin-step-up-contract-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Admin-Step-Up-123"
TENANT = "tenant-admin-step-up"
UNIDADE_A = "unidade-admin-a"
UNIDADE_B = "unidade-admin-b"


def _infra(monkeypatch, *, papel: Papel, email: str) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fm_unidade_loja_legacy_v1
                    (tenant_id, unidade_id, loja_id, ativo)
                VALUES
                    (:tenant, :unidade_a, 81, TRUE),
                    (:tenant, :unidade_b, 82, TRUE)
                """
            ),
            {
                "tenant": TENANT,
                "unidade_a": UNIDADE_A,
                "unidade_b": UNIDADE_B,
            },
        )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id=f"usuario-{papel.value}-step-up",
            email=email,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(papel,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        session.commit()

    app = build_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE_A,
        ),
        engine=engine,
        session_factory=factory,
    )
    return TestClient(app)


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": email, "senha": SENHA},
    )
    assert response.status_code == 200


def test_administrador_exige_step_up_e_revoga_ao_trocar_unidade(monkeypatch) -> None:
    email = "proprietario-step-up@example.com"
    client = _infra(monkeypatch, papel=Papel.ADMINISTRADOR, email=email)
    _login(client, email)

    inicial = client.get("/v1/auth/admin-status")
    assert inicial.status_code == 200
    assert inicial.json() == {
        "permitido": True,
        "elevado": False,
        "expira_em": None,
    }

    senha_errada = client.post(
        "/v1/auth/admin-step-up",
        json={"senha": "senha-incorreta"},
    )
    assert senha_errada.status_code == 401
    assert senha_errada.json() == {"erro": "seguranca.credenciais_invalidas"}

    elevado = client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    )
    assert elevado.status_code == 200
    assert elevado.json()["ok"] is True
    assert elevado.json()["expira_em"] is not None

    status_elevado = client.get("/v1/auth/admin-status")
    assert status_elevado.status_code == 200
    assert status_elevado.json()["permitido"] is True
    assert status_elevado.json()["elevado"] is True
    assert status_elevado.json()["expira_em"] is not None

    troca = client.post(
        "/v1/auth/select-unit",
        json={"unidade_id": UNIDADE_B},
    )
    assert troca.status_code == 200

    apos_troca = client.get("/v1/auth/admin-status")
    assert apos_troca.status_code == 200
    assert apos_troca.json() == {
        "permitido": True,
        "elevado": False,
        "expira_em": None,
    }


def test_gerente_nao_recebe_barreira_proprietario(monkeypatch) -> None:
    email = "gerente-sem-admin@example.com"
    client = _infra(monkeypatch, papel=Papel.GERENTE, email=email)
    _login(client, email)

    status_admin = client.get("/v1/auth/admin-status")
    assert status_admin.status_code == 200
    assert status_admin.json() == {
        "permitido": False,
        "elevado": False,
        "expira_em": None,
    }

    step_up = client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    )
    assert step_up.status_code == 403
    assert step_up.json() == {"erro": "seguranca.permissao_insuficiente"}


def test_catalogo_web_exige_admin_e_step_up_para_mutacao(monkeypatch) -> None:
    admin_email = "admin-catalogo-step-up@example.com"
    client = _infra(monkeypatch, papel=Papel.ADMINISTRADOR, email=admin_email)
    _login(client, admin_email)

    sem_step_up = client.post(
        "/v1/catalogo/produtos",
        headers={"Idempotency-Key": "admin-step-up-produto-001"},
        json={
            "nome": "Produto Protegido",
            "categoria": "Admin",
            "preco": 19.9,
            "ativo": True,
        },
    )
    assert sem_step_up.status_code == 403
    assert sem_step_up.json() == {"erro": "seguranca.admin_step_up_exigido"}

    step_up = client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    )
    assert step_up.status_code == 200

    com_step_up = client.post(
        "/v1/catalogo/produtos",
        headers={"Idempotency-Key": "admin-step-up-produto-001"},
        json={
            "nome": "Produto Protegido",
            "categoria": "Admin",
            "preco": 19.9,
            "ativo": True,
        },
    )
    assert com_step_up.status_code == 201
    assert com_step_up.json()["nome"] == "Produto Protegido"


def test_gerente_web_nao_pode_mutar_catalogo_mesmo_com_configuracao_alterar(
    monkeypatch,
) -> None:
    email = "gerente-catalogo-protegido@example.com"
    client = _infra(monkeypatch, papel=Papel.GERENTE, email=email)
    _login(client, email)

    response = client.post(
        "/v1/catalogo/produtos",
        headers={"Idempotency-Key": "gerente-nao-admin-produto-001"},
        json={
            "nome": "Produto Negado",
            "categoria": "Admin",
            "preco": 10,
            "ativo": True,
        },
    )
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.admin_acesso_exigido"}
