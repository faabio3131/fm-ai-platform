from __future__ import annotations

import base64

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-Segura-PDV-123"
TENANT = "tenant-pdv-http"
UNIDADE = "unidade-pdv-http"


def _infra():
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
                    (:tenant, :unidade, 71, TRUE)
                """
            ),
            {"tenant": TENANT, "unidade": UNIDADE},
        )
        conn.execute(
            text(
                """
                INSERT INTO produtos
                    (id, loja_id, nome, categoria, preco_venda)
                VALUES
                    (1, '71', 'X-Bacon', 'Lanches', 30.00),
                    (2, '71', 'Produto sem preco', 'Lanches', NULL),
                    (3, '99', 'Outro escopo', 'Lanches', 99.00)
                """
            )
        )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="caixa-pdv@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.CAIXA,),
        )
        session.commit()

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite://",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
    )
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
    )
    return engine, factory, TestClient(app)


def _headers(
    key: str = "4cdf75a2-80e1-4db8-a02c-25fd996be7e9",
) -> dict[str, str]:
    auth = base64.b64encode(
        f"caixa-pdv@example.com:{SENHA}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE,
        "Idempotency-Key": key,
        "X-Correlation-ID": "corr-pdv-http-contract",
    }


def _payload(quantidade: int = 1) -> dict[str, object]:
    return {
        "itens": [
            {
                "produto_id": "legacy:produto:1",
                "quantidade": quantidade,
                "observacoes": "sem cebola",
            }
        ],
        "metodo_pagamento": "dinheiro",
        "desconto": "0.00",
    }


def _count(session: Session, model) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_catalogo_pdv_lista_somente_produtos_ativos_do_escopo() -> None:
    _, _, client = _infra()

    response = client.get("/v1/pdv/produtos", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "produtos": [
            {
                "id": "legacy:produto:1",
                "nome": "X-Bacon",
                "categoria": "Lanches",
                "preco": "30.00",
                "disponivel": True,
            }
        ]
    }


def test_checkout_pdv_cria_pedido_e_pagamento() -> None:
    engine, _, client = _infra()

    response = client.post(
        "/v1/pdv/checkout",
        headers=_headers(),
        json=_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["idempotente"] is False
    assert body["comanda"]["status"] == "aguardando_confirmacao"
    assert body["comanda"]["total"] == "30.00"
    assert body["comanda"]["itens"][0]["produto_id"] == "legacy:produto:1"
    assert body["pagamento"]["metodo"] == "dinheiro"
    assert body["pagamento"]["valor_previsto"] == "30.00"

    with Session(engine) as session:
        assert _count(session, PedidoORM) == 1
        assert _count(session, PagamentoORM) == 1


def test_checkout_pdv_replay_exato_retorna_200_sem_duplicar() -> None:
    engine, _, client = _infra()
    headers = _headers("b3877434-abd6-4684-9cd5-baa900572231")

    primeiro = client.post(
        "/v1/pdv/checkout",
        headers=headers,
        json=_payload(),
    )
    replay = client.post(
        "/v1/pdv/checkout",
        headers=headers,
        json=_payload(),
    )

    assert primeiro.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["idempotente"] is True
    assert (
        replay.json()["comanda"]["pedido_id"]
        == primeiro.json()["comanda"]["pedido_id"]
    )
    assert replay.json()["pagamento"]["id"] == primeiro.json()["pagamento"]["id"]

    with Session(engine) as session:
        assert _count(session, PedidoORM) == 1
        assert _count(session, PagamentoORM) == 1


def test_checkout_pdv_rejeita_payload_divergente_na_mesma_chave() -> None:
    _, _, client = _infra()
    headers = _headers("a1c0b7da-c510-4948-b181-1e3f62d34360")

    primeiro = client.post(
        "/v1/pdv/checkout",
        headers=headers,
        json=_payload(1),
    )
    conflito = client.post(
        "/v1/pdv/checkout",
        headers=headers,
        json=_payload(2),
    )

    assert primeiro.status_code == 201
    assert conflito.status_code == 409
    assert conflito.json() == {"erro": "conflito_transacional"}


def test_pdv_rejeita_tenant_ou_unidade_fora_do_contexto_autenticado() -> None:
    _, _, client = _infra()
    headers = _headers()
    headers["X-Unit-ID"] = "unidade-nao-autorizada"

    response = client.post(
        "/v1/pdv/checkout",
        headers=headers,
        json=_payload(),
    )

    assert response.status_code == 401
    assert response.json() == {"erro": "seguranca.credenciais_invalidas"}


def test_checkout_pdv_consulta_apenas_itens_pedidos_em_vez_do_cardapio_inteiro() -> None:
    engine, _, client = _infra()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO produtos (id, loja_id, nome, categoria, preco_venda) "
                "VALUES (:id, '71', :nome, 'Lanches', 30.00)"
            ),
            [{"id": n, "nome": f"Extra {n}"} for n in range(100, 700)],
        )

    sqls: list[str] = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        sqls.append(statement)

    event.listen(engine, "before_cursor_execute", registrar)
    try:
        response = client.post(
            "/v1/pdv/checkout", headers=_headers(), json=_payload()
        )
    finally:
        event.remove(engine, "before_cursor_execute", registrar)

    assert response.status_code == 201, response.text
    assert response.json()["comanda"]["total"] == "30.00"
    product_sql = [
        sql for sql in sqls
        if "FROM produtos" in sql and "SELECT" in sql
    ]
    assert len(product_sql) == 1
    assert "produtos.id IN" in product_sql[0]
    assert "produtos.loja_id" in product_sql[0]

    # Listagem completa continua exibindo todos os itens válidos do escopo.
    catalog = client.get("/v1/pdv/produtos", headers=_headers())
    assert catalog.status_code == 200
    assert len(catalog.json()["produtos"]) == 601


def test_checkout_pdv_outro_escopo_ou_id_nao_canonico_rejeitado() -> None:
    engine, _, client = _infra()
    payload = _payload()
    for produto_id in (
        "legacy:produto:3",  # produto pertence a outra loja
        "legacy:produto:01",  # antes também não correspondia ao ID canônico
        "legacy:produto:999999999999999999999999999999",
        "produto:1",
    ):
        payload["itens"][0]["produto_id"] = produto_id
        response = client.post(
            "/v1/pdv/checkout",
            headers=_headers("idempotente-invalido-" + produto_id),
            json=payload,
        )
        assert response.status_code == 400
        assert response.json() == {"erro": "produto_indisponivel_ou_fora_do_escopo"}
    with Session(engine) as session:
        assert _count(session, PedidoORM) == 0
        assert _count(session, PagamentoORM) == 0
