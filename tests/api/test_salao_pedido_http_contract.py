from __future__ import annotations

import base64
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.pagamentos.modelos_orm import PagamentoORM
from core.pedidos.modelos_orm import PedidoORM
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.salao import RepositorioSalaoSQLAlchemy, ServicoSalao
from core.salao.modelos_orm import PedidoComandaORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-Segura-Salao-Pedido-123"
EMAIL = "garcom-pedido@example.com"
TENANT = "tenant-salao-pedido"
UNIDADE = "unidade-salao-pedido"
OUTRA_UNIDADE = "unidade-salao-pedido-outra"
MESA_ID = "mesa-salao-pedido-01"


def _contexto_sistema() -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="fixture-salao-pedido-http",
        motivo="preparar contrato HTTP de lançamento do Salão",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        correlation_id="fixture:salao-pedido-http",
        solicitado_em=datetime.now(timezone.utc),
    )


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
                    (:tenant, :unidade, 71, TRUE),
                    (:tenant, :outra, 72, TRUE)
                """
            ),
            {"tenant": TENANT, "unidade": UNIDADE, "outra": OUTRA_UNIDADE},
        )
        conn.execute(
            text(
                """
                INSERT INTO produtos
                    (id, loja_id, nome, categoria, preco_venda, ativo)
                VALUES
                    (1, '71', 'X-Bacon', 'Lanches', 30.00, TRUE),
                    (2, '71', 'Suco', 'Bebidas', 12.00, FALSE),
                    (3, '72', 'Pizza externa', 'Pizzas', 55.00, TRUE)
                """
            )
        )

    with factory() as session:
        ServicoSalao(
            RepositorioSalaoSQLAlchemy(session),
            agora=lambda: datetime.now(timezone.utc),
        ).cadastrar_mesa(
            _contexto_sistema(),
            mesa_id=MESA_ID,
            codigo="01",
            capacidade=4,
            idempotency_key="seed:mesa-salao-pedido",
            nome="Mesa 01",
        )
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GARCOM,),
        )
        session.commit()

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite://",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
    )
    client = TestClient(
        build_http_app(
            settings=settings,
            engine=engine,
            session_factory=factory,
        )
    )
    return engine, client


def _headers(key: str | None = None) -> dict[str, str]:
    auth = base64.b64encode(f"{EMAIL}:{SENHA}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE,
        "X-Correlation-ID": "corr-salao-pedido-http",
    }
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _abrir(client: TestClient) -> str:
    response = client.post(
        "/v1/salao/comandas/abrir",
        headers=_headers("salao-pedido-open-001"),
        json={"mesa_id": MESA_ID},
    )
    assert response.status_code == 201
    return response.json()["comanda"]["id"]


def _payload(quantidade: int = 1, produto_id: str = "legacy:produto:1"):
    return {
        "itens": [
            {
                "produto_id": produto_id,
                "quantidade": quantidade,
                "observacao": "sem cebola",
            }
        ]
    }


def test_lancamento_cria_pedido_confirmado_e_vincula_comanda_atomicamente() -> None:
    engine, client = _infra()
    comanda_id = _abrir(client)

    response = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=_headers("salao-order-001"),
        json=_payload(),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["idempotente"] is False
    assert body["comanda"]["status_comanda"] == "EM_CONSUMO"
    assert body["comanda"]["total"] == "30.00"
    assert body["comanda"]["saldo"] == "30.00"
    assert body["pedido"]["valor"] == "30.00"
    assert body["pedido"]["itens"][0]["nome"] == "X-Bacon"
    assert body["pedido"]["itens"][0]["observacao"] == "sem cebola"

    pedido_id = body["pedido"]["pedido_id"]
    with Session(engine) as session:
        pedido = session.get(PedidoORM, (pedido_id, TENANT, UNIDADE))
        assert pedido is not None
        assert pedido.status == "confirmado"
        assert pedido.canal == "salao"
        assert pedido.origem == "salao"
        assert (
            session.scalar(
                select(func.count())
                .select_from(PedidoComandaORM)
                .where(PedidoComandaORM.pedido_id == pedido_id)
            )
            == 1
        )
        assert session.scalar(select(func.count()).select_from(PagamentoORM)) == 0

    detalhe = client.get(
        f"/v1/salao/comandas/{comanda_id}",
        headers=_headers(),
    )
    assert detalhe.status_code == 200
    assert detalhe.json()["pedidos"][0]["pedido_id"] == pedido_id
    assert detalhe.json()["pedidos"][0]["itens"][0]["nome"] == "X-Bacon"


def test_lancamento_replay_retorna_200_sem_duplicar_pedido_ou_vinculo() -> None:
    engine, client = _infra()
    comanda_id = _abrir(client)
    headers = _headers("salao-order-replay-002")

    primeiro = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=headers,
        json=_payload(),
    )
    replay = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=headers,
        json=_payload(),
    )

    assert primeiro.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["idempotente"] is True
    assert replay.json()["pedido"]["pedido_id"] == primeiro.json()["pedido"]["pedido_id"]
    assert replay.json()["comanda"]["total"] == "30.00"

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PedidoORM)) == 1
        assert session.scalar(select(func.count()).select_from(PedidoComandaORM)) == 1


def test_lancamento_mesma_chave_payload_divergente_retorna_409() -> None:
    _, client = _infra()
    comanda_id = _abrir(client)
    headers = _headers("salao-order-conflict-003")

    primeiro = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=headers,
        json=_payload(1),
    )
    conflito = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=headers,
        json=_payload(2),
    )

    assert primeiro.status_code == 201
    assert conflito.status_code == 409
    assert conflito.json() == {"erro": "conflito_transacional"}


def test_lancamento_rejeita_produto_inativo_ou_de_outra_unidade() -> None:
    _, client = _infra()
    comanda_id = _abrir(client)

    inativo = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=_headers("salao-order-inactive-004"),
        json=_payload(produto_id="2"),
    )
    externo = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=_headers("salao-order-cross-unit-005"),
        json=_payload(produto_id="legacy:produto:3"),
    )

    assert inativo.status_code == 404
    assert inativo.json() == {"erro": "produto_indisponivel"}
    assert externo.status_code == 404
    assert externo.json() == {"erro": "produto_indisponivel"}


def test_lancamento_exige_credenciais_e_idempotency_key() -> None:
    _, client = _infra()
    comanda_id = _abrir(client)

    sem_credenciais = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers={"Idempotency-Key": "salao-order-no-auth-006"},
        json=_payload(),
    )
    sem_chave = client.post(
        f"/v1/salao/comandas/{comanda_id}/pedidos",
        headers=_headers(),
        json=_payload(),
    )

    assert sem_credenciais.status_code == 401
    assert sem_chave.status_code == 422
