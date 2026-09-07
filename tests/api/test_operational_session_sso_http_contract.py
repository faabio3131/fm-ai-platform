from __future__ import annotations

import base64

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "operational-sso-contract-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Operational-SSO-123"
EMAIL = "gerente-operational-sso@example.com"
TENANT = "tenant-operational-sso"
UNIDADE_A = "unidade-operational-a"
UNIDADE_B = "unidade-operational-b"


def _infra(monkeypatch) -> TestClient:
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
                    (:tenant, :unidade_a, 91, TRUE),
                    (:tenant, :unidade_b, 92, TRUE)
                """
            ),
            {
                "tenant": TENANT,
                "unidade_a": UNIDADE_A,
                "unidade_b": UNIDADE_B,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO produtos
                    (id, loja_id, nome, categoria, preco_venda, ativo)
                VALUES
                    (101, '91', 'Produto Unidade A', 'SSO', 11.00, TRUE),
                    (102, '92', 'Produto Unidade B', 'SSO', 22.00, TRUE)
                """
            )
        )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="usuario-operational-sso",
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.GERENTE,),
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


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": SENHA},
    )
    assert response.status_code == 200


def _basic_headers() -> dict[str, str]:
    auth = base64.b64encode(f"{EMAIL}:{SENHA}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE_A,
    }


def test_cookie_unificado_abre_pdv_salao_e_kds_sem_segundo_login(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    pdv = client.get("/v1/pdv/produtos")
    salao = client.get("/v1/salao/mapa")
    kds = client.get("/v1/kds/setores")

    assert pdv.status_code == 200
    assert [item["nome"] for item in pdv.json()["produtos"]] == ["Produto Unidade A"]
    assert salao.status_code == 200
    assert salao.json() == {"mesas": [], "comandas": []}
    assert kds.status_code == 200
    assert kds.json() == {"setores": []}


def test_cookie_assinado_e_autoridade_de_escopo_e_ignora_headers_spoofados(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    _login(client)

    response = client.get(
        "/v1/pdv/produtos",
        headers={
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": UNIDADE_B,
        },
    )

    assert response.status_code == 200
    assert [item["nome"] for item in response.json()["produtos"]] == [
        "Produto Unidade A"
    ]


def test_troca_de_unidade_altera_escopo_operacional_sem_novo_login(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    antes = client.get("/v1/pdv/produtos")
    assert antes.status_code == 200
    assert [item["nome"] for item in antes.json()["produtos"]] == ["Produto Unidade A"]

    troca = client.post(
        "/v1/auth/select-unit",
        json={"unidade_id": UNIDADE_B},
    )
    assert troca.status_code == 200

    depois = client.get("/v1/pdv/produtos")
    assert depois.status_code == 200
    assert [item["nome"] for item in depois.json()["produtos"]] == ["Produto Unidade B"]


def test_cookie_invalido_nao_faz_downgrade_para_basic_valido(monkeypatch) -> None:
    client = _infra(monkeypatch)
    client.cookies.set("fm_ai_session", "sessao-invalida.assinatura-invalida")

    response = client.get(
        "/v1/pdv/produtos",
        headers=_basic_headers(),
    )

    assert response.status_code == 401
    assert response.json() == {"erro": "seguranca.credenciais_invalidas"}


def test_basic_legado_permanece_compativel_sem_cookie(monkeypatch) -> None:
    client = _infra(monkeypatch)

    response = client.get(
        "/v1/pdv/produtos",
        headers=_basic_headers(),
    )

    assert response.status_code == 200
    assert [item["nome"] for item in response.json()["produtos"]] == [
        "Produto Unidade A"
    ]
