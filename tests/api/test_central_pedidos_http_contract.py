from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "orders-center-http-secret-0123456789-abcdef"
SENHA = "Senha-Segura-Orders-Center-123"
EMAIL = "gerente-orders-center@example.com"
TENANT = "tenant-orders-center-http"
UNIDADE = "unidade-orders-center-http"


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
                    (:tenant, :unidade, 501, TRUE)
                """
            ),
            {"tenant": TENANT, "unidade": UNIDADE},
        )
        conn.execute(
            text(
                """
                INSERT INTO produtos
                    (id, loja_id, nome, categoria, preco_venda, ativo)
                VALUES
                    (501, '501', 'Combo Central', 'Combos', 42.00, TRUE)
                """
            )
        )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="usuario-orders-center",
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
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


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": EMAIL, "senha": SENHA},
    )
    assert response.status_code == 200


def _criar_pedido_pdv(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/v1/pdv/checkout",
        headers={
            "Idempotency-Key": "orders-center-http-checkout-001",
            "X-Correlation-ID": "corr-orders-center-checkout",
        },
        json={
            "itens": [
                {
                    "produto_id": "legacy:produto:501",
                    "quantidade": 1,
                    "observacoes": "sem alteração",
                }
            ],
            "metodo_pagamento": "dinheiro",
            "desconto": "0.00",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_cookie_unificado_lista_e_detalha_pedido_sem_segundo_login(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    checkout = _criar_pedido_pdv(client)
    pedido_id = checkout["comanda"]["pedido_id"]

    lista = client.get("/v1/pedidos")
    detalhe = client.get(f"/v1/pedidos/{pedido_id}")

    assert lista.status_code == 200
    assert lista.json()["total"] == 1
    assert lista.json()["itens"][0]["pedido_id"] == pedido_id
    assert lista.json()["itens"][0]["total"] == "42.00"
    assert detalhe.status_code == 200
    assert detalhe.json()["resumo"]["pedido_id"] == pedido_id
    assert detalhe.json()["itens"][0]["nome"] == "Combo Central"
    assert detalhe.json()["financeiro"]["situacao"] == "pendente"


def test_cookie_assinado_governa_escopo_da_central_e_ignora_spoof(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    _criar_pedido_pdv(client)

    response = client.get(
        "/v1/pedidos",
        headers={
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": "unidade-spoof",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_central_cancela_pedido_pela_fronteira_autoritativa(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    checkout = _criar_pedido_pdv(client)
    pedido_id = checkout["comanda"]["pedido_id"]

    antes = client.get(f"/v1/pedidos/{pedido_id}")
    assert antes.status_code == 200
    versao = antes.json()["resumo"]["versao"]

    cancelado = client.post(
        f"/v1/pedidos/{pedido_id}/cancelar",
        headers={"Idempotency-Key": "orders-center-cancel-001"},
        json={
            "versao_esperada": versao,
            "motivo": "Cancelamento de contrato HTTP",
        },
    )

    assert cancelado.status_code == 200
    assert cancelado.json()["status"] == "cancelado"

    depois = client.get(f"/v1/pedidos/{pedido_id}")
    assert depois.status_code == 200
    assert depois.json()["resumo"]["status"] == "cancelado"
    assert depois.json()["resumo"]["versao"] > versao


def test_central_exige_idempotency_key_em_comando(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)
    checkout = _criar_pedido_pdv(client)
    pedido_id = checkout["comanda"]["pedido_id"]
    detalhe = client.get(f"/v1/pedidos/{pedido_id}").json()

    response = client.post(
        f"/v1/pedidos/{pedido_id}/cancelar",
        json={
            "versao_esperada": detalhe["resumo"]["versao"],
            "motivo": "sem chave",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"erro": "idempotency_key_obrigatoria"}
