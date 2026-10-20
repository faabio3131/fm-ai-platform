from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "delivery-entrega-http-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Delivery-Entrega-123"
TENANT = "tenant-delivery-entrega-http"
UNIDADE = "unidade-delivery-entrega-http"
GERENTE_EMAIL = "gerente-delivery-entrega@example.com"
COZINHA_EMAIL = "cozinha-delivery-entrega@example.com"


def _infra(monkeypatch) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        repositorio = RepositorioIdentidadesSQLAlchemy(session)
        repositorio.criar_usuario(
            usuario_id="usuario-delivery-entrega-gerente",
            email=GERENTE_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
        )
        repositorio.criar_usuario(
            usuario_id="usuario-delivery-entrega-cozinha",
            email=COZINHA_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.COZINHA,),
            unidades_permitidas=(UNIDADE,),
        )
        session.commit()

    app = build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST,
            database_url="sqlite://",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
        ),
        engine=engine,
        session_factory=factory,
    )
    return TestClient(app)


def _login(client: TestClient, email: str = GERENTE_EMAIL) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": email, "senha": SENHA},
    )
    assert response.status_code == 200


def test_delivery_and_entrega_require_authenticated_identity(monkeypatch) -> None:
    client = _infra(monkeypatch)

    delivery = client.get("/v1/delivery/clientes")
    entrega = client.get("/v1/entregas")

    assert delivery.status_code == 401
    assert delivery.json() == {"erro": "credenciais_invalidas"}
    assert entrega.status_code == 401
    assert entrega.json() == {"erro": "credenciais_invalidas"}


def test_signed_cookie_authorizes_delivery_and_entrega_without_second_login(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    delivery = client.get("/v1/delivery/clientes")
    entrega = client.get("/v1/entregas")

    assert delivery.status_code == 200
    assert delivery.json() == {"itens": []}
    assert entrega.status_code == 200
    assert entrega.json() == {"itens": []}


def test_signed_cookie_scope_ignores_tenant_and_unit_spoof_headers(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    spoof = {
        "X-Tenant-ID": "tenant-spoof",
        "X-Unit-ID": "unidade-spoof",
    }

    delivery = client.get("/v1/delivery/clientes", headers=spoof)
    entrega = client.get("/v1/entregas", headers=spoof)

    assert delivery.status_code == 200
    assert delivery.json() == {"itens": []}
    assert entrega.status_code == 200
    assert entrega.json() == {"itens": []}


def test_delivery_and_entrega_fail_closed_without_rbac(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client, COZINHA_EMAIL)

    delivery = client.get("/v1/delivery/clientes")
    entrega = client.get("/v1/entregas")

    assert delivery.status_code == 403
    assert entrega.status_code == 403


def test_delivery_confirmation_requires_idempotency_key_before_domain_lookup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    response = client.post(
        "/v1/delivery/clientes/cliente-inexistente/carrinhos/carrinho-inexistente/confirmar",
        json={"metodo_pagamento": "pix"},
    )

    assert response.status_code == 400
    assert response.json() == {"erro": "idempotency_key_obrigatoria"}


def test_entrega_commands_require_idempotency_key_before_domain_lookup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    response = client.post(
        "/v1/entregas/entrega-inexistente/coletar",
        json={"versao_esperada": 1},
    )

    assert response.status_code == 400
    assert response.json() == {"erro": "idempotency_key_obrigatoria"}
