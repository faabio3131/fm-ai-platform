from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.administracao.repositorio_sqlalchemy import RepositorioAdministracaoSQLAlchemy
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "cardapio-publico-session-secret-0123456789"
SENHA = "Senha-Segura-Cardapio-123"
TENANT = "tenant-cardapio-http"
UNIDADE = "unidade-cardapio-a"
ADMIN_EMAIL = "admin-cardapio@example.com"


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
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="admin-cardapio-user",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE,),
            acesso_admin_sensivel=True,
        )
        RepositorioAdministracaoSQLAlchemy(session).garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome_empresa="Empresa Cardapio",
            nome_unidade="Matriz Centro",
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


def _login(client: TestClient, *, elevar: bool = True) -> None:
    response = client.post("/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": SENHA})
    assert response.status_code == 200
    if elevar:
        response = client.post("/v1/auth/admin-step-up", json={"senha": SENHA})
        assert response.status_code == 200


def test_configuracao_publica_exige_sessao_e_stepup(monkeypatch) -> None:
    client = _infra(monkeypatch)
    sem_sessao = client.get(f"/v1/admin/cardapio-publico/{UNIDADE}")
    assert sem_sessao.status_code == 401

    _login(client, elevar=False)
    sem_stepup = client.get(f"/v1/admin/cardapio-publico/{UNIDADE}")
    assert sem_stepup.status_code == 403


def test_publicacao_configuravel_gera_identidade_publica_estavel(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    inicial = client.get(f"/v1/admin/cardapio-publico/{UNIDADE}")
    assert inicial.status_code == 200
    assert inicial.json()["public_id"] is None
    assert inicial.json()["publicada"] is False

    criada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 1},
    )
    assert criada.status_code == 200
    payload = criada.json()
    assert payload["slug"] == "matriz-centro"
    assert payload["publicada"] is True
    assert len(payload["public_id"]) == 32
    assert payload["url_publica"].endswith(f"/{payload['public_id']}/matriz-centro")

    alterada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Loja Centro", "publicada": True, "versao": payload["versao"]},
    )
    assert alterada.status_code == 200
    assert alterada.json()["public_id"] == payload["public_id"]
    assert alterada.json()["slug"] == "loja-centro"


def test_cardapio_publico_resolve_escopo_sem_expor_ids_internos(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    configurada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 1},
    )
    public_id = configurada.json()["public_id"]

    client.post("/v1/auth/logout")
    response = client.get(
        f"/v1/publico/cardapio/{public_id}",
        headers={"X-Tenant-ID": "tenant-forjado", "X-Unit-ID": "unidade-forjada"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["public_id"] == public_id
    assert data["slug"] == "matriz-centro"
    assert data["empresa"] == "Empresa Cardapio"
    assert data["unidade"] == "Matriz Centro"
    assert data["tipo_unidade"] == "unidade"
    assert data["itens"] == []
    assert "tenant_id" not in data
    assert "unidade_id" not in data


def test_cardapio_nao_publicado_e_id_invalido_nao_vazam_escopo(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    configurada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": False, "versao": 1},
    )
    public_id = configurada.json()["public_id"]
    client.post("/v1/auth/logout")

    oculto = client.get(f"/v1/publico/cardapio/{public_id}")
    invalido = client.get("/v1/publico/cardapio/tenant-cardapio-http")
    assert oculto.status_code == 404
    assert invalido.status_code == 404
    assert oculto.json() == {"erro": "cardapio_publico_indisponivel"}
    assert invalido.json() == {"erro": "cardapio_publico_indisponivel"}


def test_slug_invalido_e_concorrencia_sao_rejeitados(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    invalido = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "!!!", "publicada": True, "versao": 1},
    )
    assert invalido.status_code == 400

    primeira = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 1},
    )
    assert primeira.status_code == 200
    stale = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Outra Loja", "publicada": True, "versao": 1},
    )
    assert stale.status_code == 409
