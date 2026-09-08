from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.kds.modelos_orm import SetorProducaoORM
from core.pagamentos.modelos_orm import ObrigacaoPagamentoORM, PagamentoORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "order-kds-routing-secret-0123456789-abcdef"
EMAIL = "gerente-order-kds-routing@example.com"
SENHA = "Senha-Segura-Order-KDS-Routing-123"
TENANT = "tenant-order-kds-routing"
UNIDADE = "unidade-order-kds-routing"
PEDIDO_ID = "pedido-order-kds-routing"
ITEM_ID = "item-order-kds-routing"
SETOR_ID = "setor-order-kds-routing"
PAGAMENTO_ID = "pag-order-kds-routing"


def _infra(monkeypatch) -> TestClient:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    agora = datetime.now(UTC)

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            usuario_id="usuario-order-kds-routing",
            email=EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.GERENTE,),
            unidades_permitidas=(UNIDADE,),
        )
        session.add(
            PedidoORM(
                id=PEDIDO_ID,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                origem="delivery_proprio",
                canal="delivery_proprio",
                status="aguardando_confirmacao",
                cliente_id="cliente-order-kds-routing",
                criado_em=agora,
                atualizado_em=agora,
                versao=1,
                correlation_id="corr-order-kds-routing",
                idempotency_key="pedido-order-kds-routing-key",
                request_hash="a" * 64,
                subtotal=Decimal("42.00"),
                descontos=Decimal("0.00"),
                taxas=Decimal("5.00"),
                total=Decimal("47.00"),
            )
        )
        session.add(
            ItemPedidoORM(
                id=ITEM_ID,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=PEDIDO_ID,
                ordem=1,
                produto_id="produto-order-kds-routing",
                nome_produto="Combo Smoke Routing",
                quantidade=1,
                preco_unitario=Decimal("42.00"),
                subtotal=Decimal("42.00"),
                observacao=None,
                ficha_versao="delivery-catalogo-v1",
            )
        )
        session.add(
            SetorProducaoORM(
                id=SETOR_ID,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="cozinha",
                nome="Cozinha Homologação",
                ordem=1,
                sla_segundos=600,
                ativo=True,
                criado_em=agora,
                atualizado_em=agora,
            )
        )
        session.add(
            ObrigacaoPagamentoORM(
                id=PAGAMENTO_ID,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=PEDIDO_ID,
                comanda_id=None,
                valor_previsto=Decimal("47.00"),
                moeda="BRL",
                criado_em=agora,
                versao=1,
                correlation_id="corr-order-kds-routing",
                idempotency_key="obrigacao-order-kds-routing",
                request_hash="b" * 64,
            )
        )
        session.flush()
        session.add(
            PagamentoORM(
                id=PAGAMENTO_ID,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=PEDIDO_ID,
                comanda_id=None,
                status="pendente",
                metodo="pagamento_na_entrega",
                valor_previsto=Decimal("47.00"),
                valor_pago=Decimal("0.00"),
                valor_estornado=Decimal("0.00"),
                saldo=Decimal("47.00"),
                moeda="BRL",
                recebimento_posterior=True,
                provedor=None,
                criado_em=agora,
                atualizado_em=agora,
                versao=1,
                correlation_id="corr-order-kds-routing",
                idempotency_key="pagamento-order-kds-routing",
                request_hash="c" * 64,
            )
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


def test_confirmacao_e_roteamento_kds_usam_fluxo_canonico_e_sessao_assinada(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    _login(client)

    confirmado = client.post(
        f"/v1/pedidos/{PEDIDO_ID}/confirmar",
        headers={
            "Idempotency-Key": "confirmar-order-kds-routing",
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": "unidade-spoof",
        },
        json={"versao_esperada": 1},
    )
    assert confirmado.status_code == 200
    assert confirmado.json()["status"] == "confirmado"
    assert confirmado.json()["versao"] == 2

    pendentes = client.get(
        "/v1/kds/roteamento-pendente",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": "unidade-spoof"},
    )
    assert pendentes.status_code == 200
    assert pendentes.json()["itens"] == [
        {
            "pedido_id": PEDIDO_ID,
            "pedido_item_id": ITEM_ID,
            "nome_produto": "Combo Smoke Routing",
            "quantidade": "1",
            "status_pedido": "confirmado",
        }
    ]

    roteado = client.post(
        "/v1/kds/rotear",
        headers={
            "Idempotency-Key": "rotear-order-kds-routing",
            "X-Tenant-ID": "tenant-spoof",
            "X-Unit-ID": "unidade-spoof",
        },
        json={"pedido_item_id": ITEM_ID, "setor_id": SETOR_ID, "prioridade": 7},
    )
    assert roteado.status_code == 200
    assert roteado.json()["status"] == "aguardando"
    assert roteado.json()["pedido_status"] == "enviado_producao"
    assert roteado.json()["setor_id"] == SETOR_ID

    fila = client.get("/v1/kds/fila")
    assert fila.status_code == 200
    assert len(fila.json()["tickets"]) == 1
    ticket = fila.json()["tickets"][0]
    assert ticket["pedido_id"] == PEDIDO_ID
    assert ticket["pedido_item_id"] == ITEM_ID
    assert ticket["setor_id"] == SETOR_ID
    assert ticket["prioridade"] == 7

    depois = client.get(f"/v1/pedidos/{PEDIDO_ID}")
    assert depois.status_code == 200
    assert depois.json()["resumo"]["status"] == "enviado_producao"
