from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "wp033-session-secret-01234567890123456789"
SENHA = "Senha-WP033-Segura-123"
TENANT = "tenant-wp033"
UNIDADE = "unidade-wp033"
OUTRA_UNIDADE = "unidade-wp033-b"
ADMIN_EMAIL = "admin-wp033@example.com"


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
        repo.criar_usuario(
            usuario_id="admin-wp033",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE, OUTRA_UNIDADE),
            acesso_admin_sensivel=True,
        )
        repo.criar_usuario(
            usuario_id="gerente-wp033",
            email="gerente-wp033@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
            acesso_admin_sensivel=False,
        )
        auditoria = RepositorioAuditoriaSQLAlchemy(session)
        base = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
        for idx, unidade in enumerate((UNIDADE, UNIDADE, OUTRA_UNIDADE), start=1):
            auditoria.adicionar(
                EventoAuditoria(
                    audit_id=f"audit-wp033-{idx}",
                    tenant_id=TENANT,
                    unidade_id=unidade,
                    usuario_id="admin-wp033",
                    papel_efetivo=Papel.ADMINISTRADOR,
                    acao="pedido.atualizar" if idx != 2 else "usuario.alterar",
                    recurso_tipo="pedido" if idx != 2 else "usuario",
                    recurso_id=f"recurso-{idx}",
                    resultado="sucesso" if idx != 2 else "negado",
                    motivo="teste wp033",
                    correlation_id=f"corr-wp033-{idx}",
                    timestamp=base + timedelta(minutes=idx),
                    origem="test_wp033",
                    politica="policy.wp033",
                    metadata=(("token_debug", "NAO_EXPOR"),),
                )
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


def _login(client: TestClient, email: str = ADMIN_EMAIL, *, stepup: bool = True) -> None:
    assert client.post(
        "/v1/auth/login",
        json={"email": email, "senha": SENHA},
    ).status_code == 200
    if stepup:
        assert client.post(
            "/v1/auth/admin-step-up",
            json={"senha": SENHA},
        ).status_code == 200


def test_auditoria_exige_sessao_admin_permissao_e_stepup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    assert client.get("/v1/admin/auditoria").status_code == 401

    _login(client, "gerente-wp033@example.com", stepup=False)
    assert client.get("/v1/admin/auditoria").status_code == 403

    client = _infra(monkeypatch)
    _login(client, stepup=False)
    sem_stepup = client.get("/v1/admin/auditoria")
    assert sem_stepup.status_code == 403
    assert sem_stepup.json() == {"erro": "seguranca.admin_step_up_exigido"}


def test_auditoria_respeita_unidade_ativa_e_minimiza_payload(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    response = client.get(
        "/v1/admin/auditoria",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": OUTRA_UNIDADE},
    )
    assert response.status_code == 200
    data = response.json()
    assert {item["audit_id"] for item in data["eventos"]} == {
        "audit-wp033-1",
        "audit-wp033-2",
    }
    body = str(data)
    assert "audit-wp033-3" not in body
    assert "token_debug" not in body
    assert "NAO_EXPOR" not in body
    assert "metadata" not in body
    assert "antes_resumido" not in body
    assert "depois_resumido" not in body


def test_auditoria_filtra_e_pagina(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    filtrado = client.get(
        "/v1/admin/auditoria?resultado=negado&recurso_tipo=usuario"
    )
    assert filtrado.status_code == 200
    assert [item["audit_id"] for item in filtrado.json()["eventos"]] == [
        "audit-wp033-2"
    ]

    pagina = client.get("/v1/admin/auditoria?pagina=1&tamanho=1")
    assert pagina.status_code == 200
    assert len(pagina.json()["eventos"]) == 1
    assert pagina.json()["tem_mais"] is True

    segunda = client.get("/v1/admin/auditoria?pagina=2&tamanho=1")
    assert segunda.status_code == 200
    assert len(segunda.json()["eventos"]) == 1
    assert segunda.json()["tem_mais"] is False
