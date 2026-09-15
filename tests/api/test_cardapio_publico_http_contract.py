from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "cardapio-publico-session-secret-0123456789"
SENHA = "Senha-Segura-Cardapio-123"
TENANT = "tenant-cardapio-http"
UNIDADE = "unidade-cardapio-a"
FILIAL = "unidade-cardapio-filial"
ADMIN_EMAIL = "admin-cardapio@example.com"
TENANT_B = "tenant-cardapio-b"
UNIDADE_B = "unidade-cardapio-b"
ADMIN_EMAIL_B = "admin-cardapio-b@example.com"


def _criar_identidade(
    session,
    *,
    usuario_id: str,
    email: str,
    tenant_id: str,
    unidade_id: str,
    unidades_permitidas: tuple[str, ...],
) -> None:
    RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
        usuario_id=usuario_id,
        email=email,
        password=SENHA,
        tenant_id=tenant_id,
        unidade_padrao_id=unidade_id,
        papeis=(Papel.ADMINISTRADOR,),
        unidades_permitidas=unidades_permitidas,
        acesso_admin_sensivel=True,
    )


def _seed_catalogo_primario(session) -> None:
    session.execute(text("INSERT INTO lojas (id, nome_fantasia) VALUES (101, 'Loja Cardapio HTTP')"))
    session.execute(
        text(
            "INSERT INTO fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) "
            "VALUES (:tenant, :unidade, 101, TRUE)"
        ),
        {"tenant": TENANT, "unidade": UNIDADE},
    )
    session.execute(
        text(
            "INSERT INTO produtos "
            "(id, nome, categoria, descricao_bruta, descricao_ai, preco_venda, "
            "custo_total_cmv, margem_exibicao, imagem_path, loja_id) "
            "VALUES (101, 'Burger Publico', 'Lanches', '', '', 32.00, 12.00, '', NULL, 101)"
        )
    )
    session.execute(
        text(
            "INSERT INTO insumos "
            "(id, nome, unidade_medida, saldo_atual, estoque_minimo, custo_unitario, "
            "data_fabricacao, data_validade, dias_alerta_vencimento, loja_id) "
            "VALUES (101, 'Burger Base Publico', 'un', 30, 2, 12.00, NULL, NULL, 15, 101)"
        )
    )
    session.execute(
        text(
            "INSERT INTO fichas_tecnicas "
            "(id, produto_id, insumo_id, quantidade_utilizada) VALUES (101, 101, 101, 1)"
        )
    )


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
        admin = RepositorioAdministracaoSQLAlchemy(session)
        admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome_empresa="Empresa Cardapio",
            nome_unidade="Matriz Centro",
        )
        admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=FILIAL,
            nome_empresa="Empresa Cardapio",
            nome_unidade="Filial Norte",
        )
        admin.garantir_escopo(
            tenant_id=TENANT_B,
            unidade_id=UNIDADE_B,
            nome_empresa="Empresa Independente",
            nome_unidade="Loja B",
        )
        _criar_identidade(
            session,
            usuario_id="admin-cardapio-user",
            email=ADMIN_EMAIL,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            unidades_permitidas=(UNIDADE, FILIAL),
        )
        _criar_identidade(
            session,
            usuario_id="admin-cardapio-b-user",
            email=ADMIN_EMAIL_B,
            tenant_id=TENANT_B,
            unidade_id=UNIDADE_B,
            unidades_permitidas=(UNIDADE_B,),
        )
        _seed_catalogo_primario(session)
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


def _login(
    client: TestClient,
    *,
    elevar: bool = True,
    email: str = ADMIN_EMAIL,
) -> None:
    response = client.post("/v1/auth/login", json={"email": email, "senha": SENHA})
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
    assert inicial.json()["versao"] == 0

    criada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 0},
    )
    assert criada.status_code == 200
    payload = criada.json()
    assert payload["slug"] == "matriz-centro"
    assert payload["publicada"] is True
    assert payload["versao"] == 1
    assert len(payload["public_id"]) == 32
    assert payload["url_publica"].endswith(f"/{payload['public_id']}/matriz-centro")

    alterada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Loja Centro", "publicada": True, "versao": payload["versao"]},
    )
    assert alterada.status_code == 200
    assert alterada.json()["public_id"] == payload["public_id"]
    assert alterada.json()["slug"] == "loja-centro"
    assert alterada.json()["versao"] == 2


def test_cardapio_publico_resolve_escopo_sem_expor_ids_internos(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    configurada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 0},
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
    assert data["itens"][0]["produto_id"] == "legacy:produto:101"
    assert data["itens"][0]["preco"] == "32.00"
    assert "tenant_id" not in data
    assert "unidade_id" not in data


def test_matriz_filial_e_segundo_cliente_sao_configuraveis_e_isolados(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    matriz = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 0},
    )
    filial = client.put(
        f"/v1/admin/cardapio-publico/{FILIAL}",
        json={"slug": "Filial Norte", "publicada": True, "versao": 0},
    )
    assert matriz.status_code == 200
    assert filial.status_code == 200
    assert matriz.json()["public_id"] != filial.json()["public_id"]

    client.post("/v1/auth/logout")
    _login(client, email=ADMIN_EMAIL_B)
    cliente_b = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE_B}",
        json={"slug": "Loja Cliente B", "publicada": True, "versao": 0},
    )
    assert cliente_b.status_code == 200
    assert cliente_b.json()["public_id"] not in {
        matriz.json()["public_id"],
        filial.json()["public_id"],
    }

    client.post("/v1/auth/logout")
    publico_matriz = client.get(f"/v1/publico/cardapio/{matriz.json()['public_id']}")
    publico_filial = client.get(f"/v1/publico/cardapio/{filial.json()['public_id']}")
    publico_b = client.get(f"/v1/publico/cardapio/{cliente_b.json()['public_id']}")
    assert publico_matriz.json()["unidade"] == "Matriz Centro"
    assert publico_filial.json()["unidade"] == "Filial Norte"
    assert publico_b.json()["empresa"] == "Empresa Independente"
    assert publico_b.json()["unidade"] == "Loja B"
    for resposta in (publico_matriz, publico_filial, publico_b):
        assert resposta.status_code == 200
        assert "tenant_id" not in resposta.json()
        assert "unidade_id" not in resposta.json()


def test_checkout_publico_usa_escopo_e_preco_canonicos(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    configurada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 0},
    )
    assert configurada.status_code == 200
    public_id = configurada.json()["public_id"]
    client.post("/v1/auth/logout")

    payload = {
        "itens": [{"produto_id": "legacy:produto:101", "quantidade": 2}],
        "metodo_pagamento": "pagamento_na_entrega",
        "idempotency_key": "public-checkout-http-001",
    }
    resposta = client.post(
        f"/v1/publico/cardapio/{public_id}/checkout",
        json=payload,
        headers={"X-Tenant-ID": TENANT_B, "X-Unit-ID": UNIDADE_B},
    )
    assert resposta.status_code == 200, resposta.text
    body = resposta.json()
    assert body["status"] == "aguardando_confirmacao"
    assert body["total"] == "64.00"
    assert body["pedido_id"]
    assert body["pagamento_id"]

    repetida = client.post(
        f"/v1/publico/cardapio/{public_id}/checkout",
        json=payload,
    )
    assert repetida.status_code == 200, repetida.text
    assert repetida.json()["pedido_id"] == body["pedido_id"]
    assert repetida.json()["total"] == "64.00"


def test_cardapio_nao_publicado_e_id_invalido_nao_vazam_escopo(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    configurada = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": False, "versao": 0},
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
        json={"slug": "!!!", "publicada": True, "versao": 0},
    )
    assert invalido.status_code == 400

    primeira = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Matriz Centro", "publicada": True, "versao": 0},
    )
    assert primeira.status_code == 200
    stale = client.put(
        f"/v1/admin/cardapio-publico/{UNIDADE}",
        json={"slug": "Outra Loja", "publicada": True, "versao": 0},
    )
    assert stale.status_code == 409
