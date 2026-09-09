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
        conn.execute(
            text(
                """
                INSERT INTO insumos
                    (id, loja_id, nome, unidade_medida, saldo_atual,
                     estoque_minimo, custo_unitario, data_validade,
                     dias_alerta_vencimento)
                VALUES
                    (11, 71, 'Carne', 'kg', 10.0, 2.0, 30.0,
                     '2026-12-31', 15),
                    (12, 71, 'Pão', 'un', 50.0, 10.0, 1.5,
                     '2026-10-01', 10),
                    (21, 72, 'Queijo', 'kg', 5.0, 1.0, 40.0,
                     '2026-11-15', 15)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO fichas_tecnicas
                    (id, produto_id, insumo_id, quantidade_utilizada)
                VALUES
                    (31, 1, 11, 0.18),
                    (32, 1, 12, 1.0)
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


def test_catalogo_expoe_insumos_e_ficha_somente_da_unidade() -> None:
    _, _, client = _infra()

    insumos = client.get("/v1/catalogo/insumos-ficha", headers=_headers())
    ficha = client.get("/v1/catalogo/produtos/1/ficha", headers=_headers())

    assert insumos.status_code == 200
    assert [item["id"] for item in insumos.json()] == ["11", "12"]
    assert all(item["id"] != "21" for item in insumos.json())
    assert ficha.status_code == 200
    assert ficha.json()["produto"]["id"] == "1"
    assert [item["insumo_id"] for item in ficha.json()["itens"]] == ["11", "12"]


def test_catalogo_cria_prato_e_ficha_atomicamente_e_idempotente() -> None:
    engine, _, client = _infra()
    headers = _headers(key="catalogo-ficha-idempotente-001")
    payload = {
        "nome": "Burger com ficha",
        "categoria": "Lanches",
        "preco": 42.0,
        "custo_total_cmv": 6.9,
        "margem_exibicao": "83.6%",
        "descricao_bruta": "Carne e pão",
        "ativo": True,
        "itens_ficha": [
            {"insumo_id": 11, "quantidade": 0.18},
            {"insumo_id": 12, "quantidade": 1.0},
        ],
    }

    primeiro = client.post(
        "/v1/catalogo/pratos-com-ficha",
        headers=headers,
        json=payload,
    )
    replay = client.post(
        "/v1/catalogo/pratos-com-ficha",
        headers=headers,
        json=payload,
    )

    assert primeiro.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == primeiro.json()

    produto_id = int(primeiro.json()["id"])
    ficha = client.get(
        f"/v1/catalogo/produtos/{produto_id}/ficha",
        headers=_headers(),
    )
    assert ficha.status_code == 200
    assert len(ficha.json()["itens"]) == 2

    with engine.begin() as conn:
        total_produtos = conn.execute(
            text("SELECT COUNT(*) FROM produtos WHERE nome = 'Burger com ficha'")
        ).scalar_one()
        total_fichas = conn.execute(
            text(
                "SELECT COUNT(*) FROM fichas_tecnicas "
                "WHERE produto_id = :produto_id"
            ),
            {"produto_id": produto_id},
        ).scalar_one()
    assert int(total_produtos) == 1
    assert int(total_fichas) == 2


def test_catalogo_rejeita_ficha_com_insumo_de_outra_unidade_e_faz_rollback() -> None:
    engine, _, client = _infra()

    response = client.post(
        "/v1/catalogo/pratos-com-ficha",
        headers=_headers(key="catalogo-ficha-cross-unit"),
        json={
            "nome": "Prato inválido",
            "categoria": "Teste",
            "preco": 10.0,
            "custo_total_cmv": 1.0,
            "margem_exibicao": "90%",
            "descricao_bruta": "",
            "ativo": True,
            "itens_ficha": [{"insumo_id": 21, "quantidade": 1.0}],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"erro": "catalogo.escopo_indisponivel"}
    with engine.begin() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM produtos WHERE nome = 'Prato inválido'")
        ).scalar_one()
    assert int(total) == 0


def test_estoque_lista_cria_aplica_leitura_e_exclui_no_escopo() -> None:
    _, _, client = _infra()

    inicial = client.get("/v1/estoque/insumos", headers=_headers())
    criado = client.post(
        "/v1/estoque/insumos",
        headers=_headers(),
        json={
            "nome": "Tomate",
            "unidade_medida": "kg",
            "saldo_atual": 4.0,
            "estoque_minimo": 1.0,
            "custo_unitario": 8.0,
            "data_fabricacao": None,
            "data_validade": "2026-10-20",
            "dias_alerta_vencimento": 15,
        },
    )
    leitura = client.post(
        "/v1/estoque/leituras",
        headers=_headers(),
        json={
            "itens": [
                {
                    "nome": "Tomate",
                    "quantidade": 2.0,
                    "unidade": "kg",
                    "data_validade": "2026-10-25",
                }
            ]
        },
    )
    removido = client.delete(
        f"/v1/estoque/insumos/{criado.json()['id']}",
        headers=_headers(),
    )

    assert inicial.status_code == 200
    assert [item["id"] for item in inicial.json()["itens"]] == ["11", "12"]
    assert criado.status_code == 201
    assert criado.json()["saldo_atual"] == 4.0
    assert leitura.status_code == 200
    tomate = next(item for item in leitura.json()["itens"] if item["nome"] == "Tomate")
    assert tomate["saldo_atual"] == 6.0
    assert removido.status_code == 200
    assert removido.json() == {"ok": True}


def test_estoque_nao_expoe_insumo_de_outra_unidade() -> None:
    _, _, client = _infra()

    unidade_a = client.get("/v1/estoque/insumos", headers=_headers())
    unidade_b = client.get(
        "/v1/estoque/insumos",
        headers=_headers(unidade_id=UNIDADE_B),
    )
    exclusao_cruzada = client.delete(
        "/v1/estoque/insumos/21",
        headers=_headers(),
    )

    assert all(item["id"] != "21" for item in unidade_a.json()["itens"])
    assert [item["id"] for item in unidade_b.json()["itens"]] == ["21"]
    assert exclusao_cruzada.status_code == 404
    assert exclusao_cruzada.json() == {"erro": "estoque.insumo_nao_encontrado"}
