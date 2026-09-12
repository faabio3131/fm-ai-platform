from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-Backoffice-Teste-123"
TENANT = "tenant-backoffice"
UNIDADE_A = "backoffice-a"
UNIDADE_B = "backoffice-b"


def _infra(monkeypatch, papel=Papel.ADMINISTRADOR):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", "backoffice-session-secret-01234567890123")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="backoffice-user",
            email="backoffice@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(papel,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        session.commit()
    client = TestClient(build_frontend_http_app(
        settings=RuntimeSettings(
            environment=RuntimeEnvironment.TEST, database_url="sqlite://",
            tenant_id=TENANT, unidade_id=UNIDADE_A,
        ),
        engine=engine, session_factory=factory,
    ))
    return client, factory


def _login(client, *, elevar=True):
    assert client.post("/v1/auth/login", json={
        "email": "backoffice@example.com", "senha": SENHA,
    }).status_code == 200
    if elevar:
        assert client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200


def test_acesso_exige_sessao_stepup_e_revoga_troca_logout(monkeypatch):
    client, _ = _infra(monkeypatch)
    assert client.post("/v1/admin/acesso").status_code == 401
    _login(client, elevar=False)
    assert client.post("/v1/admin/acesso").json() == {
        "erro": "seguranca.admin_step_up_exigido"
    }
    assert client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200
    assert client.post("/v1/admin/acesso").status_code == 200
    assert client.post("/v1/auth/select-unit", json={"unidade_id": UNIDADE_B}).status_code == 200
    assert client.post("/v1/admin/acesso").status_code == 403
    assert client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 200
    assert client.post("/v1/admin/acesso").status_code == 200
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.post("/v1/admin/acesso").status_code == 401


@pytest.mark.parametrize("papel", [Papel.GERENTE, Papel.COZINHA])
def test_sem_admin_nao_recebe_acesso_automatico(monkeypatch, papel):
    client, _ = _infra(monkeypatch, papel)
    _login(client, elevar=False)
    assert client.post("/v1/admin/acesso").json() == {
        "erro": "seguranca.admin_acesso_exigido"
    }
    assert client.post("/v1/auth/admin-step-up", json={"senha": SENHA}).status_code == 403


def test_acesso_audita_pela_autoridade_original_com_escopo_da_sessao(monkeypatch):
    client, factory = _infra(monkeypatch)
    _login(client)
    response = client.post(
        "/v1/admin/acesso?tenant_id=outro&unidade_id=outra",
        headers={"X-Tenant-ID": "outro", "X-Unit-ID": "outra", "X-Correlation-ID": "wp020"},
    )
    assert response.status_code == 200
    with factory() as session:
        eventos = RepositorioAuditoriaSQLAlchemy(session).listar(
            tenant_id=TENANT, unidade_id=UNIDADE_A, limite=100
        )
    acessos = [e for e in eventos if e.acao == "administracao.acessar"]
    assert len(acessos) == 1
    assert acessos[0].usuario_id == "backoffice-user"
    assert acessos[0].correlation_id == "wp020"
    assert acessos[0].politica == "administracao_proprietario_v1"
