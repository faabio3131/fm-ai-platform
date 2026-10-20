from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.notificacoes_internas.modelos import CanalNotificacaoInterna
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from core.seguranca.segredos import SecretValue
from http_api.frontend_app import build_frontend_http_app
from infra.notificacoes_internas.repositorio_sqlalchemy import (
    RepositorioNotificacoesInternasSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "wp032-session-secret-01234567890123456789"
SENHA = "Senha-WP032-Segura-123"
TENANT = "tenant-wp032"
UNIDADE = "unidade-wp032"
OUTRA_UNIDADE = "unidade-wp032-b"
ADMIN_EMAIL = "admin-wp032@example.com"


def _infra(monkeypatch):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    monkeypatch.setenv(
        "FM_AI_SECRET_MASTER_KEY",
        Fernet.generate_key().decode("ascii"),
    )
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
            usuario_id="admin-wp032",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE, OUTRA_UNIDADE),
            acesso_admin_sensivel=True,
        )
        repo.criar_usuario(
            usuario_id="gerente-wp032",
            email="gerente-wp032@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
            acesso_admin_sensivel=False,
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
    return TestClient(app), factory


def _login(
    client: TestClient,
    email: str = ADMIN_EMAIL,
    *,
    stepup: bool = True,
) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": email, "senha": SENHA},
    )
    assert response.status_code == 200
    if stepup:
        response = client.post(
            "/v1/auth/admin-step-up",
            json={"senha": SENHA},
        )
        assert response.status_code == 200


def test_listagem_exige_sessao_e_permissoes(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    assert client.get("/v1/admin/notificacoes").status_code == 401
    _login(client, "gerente-wp032@example.com", stepup=False)
    assert client.get("/v1/admin/notificacoes").status_code == 403


def test_configuracao_exige_stepup_e_nunca_expoe_contato_bruto(
    monkeypatch,
) -> None:
    client, _ = _infra(monkeypatch)
    _login(client, stepup=False)
    payload = {
        "destinatario_id": "dest-1",
        "nome_exibicao": "Gerência",
        "cargo": "Gerente",
        "contato": "+55 11 99999-1234",
        "receber_alertas_estoque": True,
        "ativo": True,
    }
    sem_stepup = client.put(
        "/v1/admin/notificacoes/dest-1",
        json=payload,
    )
    assert sem_stepup.status_code == 403
    assert sem_stepup.json() == {
        "erro": "seguranca.admin_step_up_exigido"
    }

    assert client.post(
        "/v1/auth/admin-step-up",
        json={"senha": SENHA},
    ).status_code == 200
    response = client.put(
        "/v1/admin/notificacoes/dest-1",
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["contato_mascara"] == "***1234"
    assert "contato" not in data
    assert "referencia_contato" not in data

    listing = client.get("/v1/admin/notificacoes")
    assert listing.status_code == 200
    body = str(listing.json())
    assert "999991234" not in body
    assert "+55 11 99999-1234" not in body


def test_preferencias_e_isolamento_por_unidade(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client)
    payload = {
        "destinatario_id": "dest-a",
        "nome_exibicao": "Responsável A",
        "cargo": None,
        "contato": "5511987654321",
        "receber_alertas_estoque": True,
        "ativo": True,
    }
    assert client.put(
        "/v1/admin/notificacoes/dest-a",
        json=payload,
    ).status_code == 200

    updated = client.patch(
        "/v1/admin/notificacoes/dest-a/preferencias",
        json={"receber_alertas_estoque": False, "ativo": True},
    )
    assert updated.status_code == 200
    assert updated.json()["receber_alertas_estoque"] is False

    with factory() as session:
        identidade = RepositorioIdentidadesSQLAlchemy(
            session
        ).obter_por_email(ADMIN_EMAIL)
        assert identidade is not None
        contexto_b = identidade.no_escopo_ativo(
            tenant_id=TENANT,
            unidade_id=OUTRA_UNIDADE,
        ).contexto(origem="wp032.seed")
        repo = RepositorioNotificacoesInternasSQLAlchemy(session)
        repo.configurar(
            contexto=contexto_b,
            destinatario_id="dest-b",
            nome_exibicao="Responsável B",
            cargo=None,
            canal=CanalNotificacaoInterna.WHATSAPP,
            contato=SecretValue("5511977778888"),
            receber_alertas_estoque=True,
            ativo=True,
        )
        session.commit()

    listing = client.get("/v1/admin/notificacoes")
    assert listing.status_code == 200
    ids = {
        item["destinatario_id"]
        for item in listing.json()["destinatarios"]
    }
    assert ids == {"dest-a"}

    cross = client.patch(
        "/v1/admin/notificacoes/dest-b/preferencias",
        json={"receber_alertas_estoque": False, "ativo": False},
    )
    assert cross.status_code == 403


def test_id_divergente_e_contato_invalido_falham_fechado(
    monkeypatch,
) -> None:
    client, _ = _infra(monkeypatch)
    _login(client)
    divergente = client.put(
        "/v1/admin/notificacoes/dest-url",
        json={
            "destinatario_id": "dest-body",
            "nome_exibicao": "Teste",
            "cargo": None,
            "contato": "5511999999999",
            "receber_alertas_estoque": True,
            "ativo": True,
        },
    )
    assert divergente.status_code == 400

    invalido = client.put(
        "/v1/admin/notificacoes/dest-url",
        json={
            "destinatario_id": "dest-url",
            "nome_exibicao": "Teste",
            "cargo": None,
            "contato": "123",
            "receber_alertas_estoque": True,
            "ativo": True,
        },
    )
    assert invalido.status_code == 422
