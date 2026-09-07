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

SESSION_SECRET = "catalogo-http-session-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Catalogo-123"
EMAIL = "gerente-catalogo@example.com"
TENANT = "tenant-catalogo-http"
UNIDADE_A = "unidade-catalogo-a"
UNIDADE_B = "unidade-catalogo-b"


def _infra(monkeypatch=None):
    if monkeypatch is not None:
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
                    (:tenant, :unidade_a, 71, TRUE),
                    (:tenant, :unidade_b, 72, TRUE)
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
                    (1, '71', 'X-Bacon', 'Lanches', 30.00, TRUE),
                    (2, '71', 'Suco', 'Bebidas', 12.00, FALSE),
                    (3, '72', 'Pizza', 'Pizzas', 55.00, TRUE)
                """
            )
        )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
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
    return engine, factory, TestClient(app)


def _headers(
    *,
    unidade_id: str = UNIDADE_A,
    key: str = "catalogo-idempotency-key-001",
) -> dict[str, str]:
    auth = base64.b64encode(f"{EMAIL}:{SENHA}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": unidade_id,
        "Idempotency-Key": key,
        "X-Correlation-ID": "corr-catalogo-http-contract",
    }


def test_catalogo_lista_e_filtra_produtos_por_unidade() -> None:
    _, _, client = _infra()

    todos = client.get("/v1/catalogo/produtos", headers=_headers())
    ativos = client.get(
        "/v1/catalogo/produtos?apenas_ativos=true",
        headers=_headers(),
    )
    bebidas = client.get(
        "/v1/catalogo/produtos?categoria=Bebidas",
        headers=_headers(),
    )

    assert todos.status_code == 200
    assert [produto["id"] for produto in todos.json()] == ["1", "2"]
    assert [produto["id"] for produto in ativos.json()] == ["1"]
    assert [produto["id"] for produto in bebidas.json()] == ["2"]
    assert all(produto["id"] != "3" for produto in todos.json())


def test_catalogo_retorna_categorias_distintas_da_unidade() -> None:
    _, _, client = _infra()

    response = client.get("/v1/catalogo/categorias", headers=_headers())

    assert response.status_code == 200
    assert response.json() == ["Bebidas", "Lanches"]


def test_catalogo_cadastra_inativo_e_reflete_persistencia() -> None:
    engine, _, client = _infra()

    response = client.post(
        "/v1/catalogo/produtos",
        headers=_headers(key="catalogo-create-inativo"),
        json={
            "nome": "Brownie",
            "categoria": "Sobremesas",
            "preco": 18.5,
            "ativo": False,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["nome"] == "Brownie"
    assert body["preco"] == 18.5
    assert body["ativo"] is False

    listado = client.get("/v1/catalogo/produtos", headers=_headers())
    assert any(
        produto["nome"] == "Brownie" and produto["ativo"] is False
        for produto in listado.json()
    )

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT ativo FROM produtos "
                "WHERE loja_id = '71' AND nome = 'Brownie'"
            )
        ).one()
    assert bool(row.ativo) is False


def test_catalogo_patch_altera_preco_e_ativo() -> None:
    _, _, client = _infra()

    response = client.patch(
        "/v1/catalogo/produtos/2",
        headers=_headers(),
        json={"preco": 14.75, "ativo": True},
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": "2",
        "nome": "Suco",
        "categoria": "Bebidas",
        "preco": 14.75,
        "ativo": True,
    }


def test_catalogo_isola_produto_de_outra_unidade() -> None:
    _, _, client = _infra()

    lista_a = client.get("/v1/catalogo/produtos", headers=_headers())
    patch_cross = client.patch(
        "/v1/catalogo/produtos/3",
        headers=_headers(),
        json={"ativo": False},
    )
    lista_b = client.get(
        "/v1/catalogo/produtos",
        headers=_headers(unidade_id=UNIDADE_B),
    )

    assert all(produto["id"] != "3" for produto in lista_a.json())
    assert patch_cross.status_code == 404
    assert patch_cross.json() == {"erro": "catalogo.produto_nao_encontrado"}
    assert [produto["id"] for produto in lista_b.json()] == ["3"]


def test_catalogo_post_replay_idempotente_nao_duplica() -> None:
    engine, _, client = _infra()
    headers = _headers(key="catalogo-replay-001")
    payload = {
        "nome": "Café",
        "categoria": "Bebidas",
        "preco": 7.0,
        "ativo": True,
    }

    primeiro = client.post(
        "/v1/catalogo/produtos",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        "/v1/catalogo/produtos",
        headers=headers,
        json=payload,
    )

    assert primeiro.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == primeiro.json()

    with engine.begin() as conn:
        total = conn.execute(
            text(
                "SELECT COUNT(*) FROM produtos "
                "WHERE loja_id = '71' AND nome = 'Café'"
            )
        ).scalar_one()
    assert int(total) == 1


def test_catalogo_aceita_sessao_ativa_e_troca_de_unidade(monkeypatch) -> None:
    _, _, client = _infra(monkeypatch)

    login = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": SENHA},
    )
    assert login.status_code == 200

    unidade_a = client.get("/v1/catalogo/produtos")
    assert unidade_a.status_code == 200
    assert [produto["id"] for produto in unidade_a.json()] == ["1", "2"]

    troca = client.post(
        "/v1/auth/select-unit",
        json={"unidade_id": UNIDADE_B},
    )
    assert troca.status_code == 200

    unidade_b = client.get("/v1/catalogo/produtos")
    assert unidade_b.status_code == 200
    assert [produto["id"] for produto in unidade_b.json()] == ["3"]


def test_catalogo_rejeita_ausencia_de_credenciais() -> None:
    _, _, client = _infra()

    response = client.get("/v1/catalogo/produtos")

    assert response.status_code == 401
    assert response.json() == {"erro": "seguranca.credenciais_invalidas"}
