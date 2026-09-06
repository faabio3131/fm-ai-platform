from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.kds.modelos_orm import ProducaoItemORM, SetorProducaoORM
from core.pedidos.modelos_orm import ItemPedidoORM, PedidoORM
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-Segura-KDS-123"
TENANT = "tenant-kds-http"
UNIDADE = "unidade-kds-http"
TENANT_OUTRO = "tenant-kds-http-outro"
UNIDADE_OUTRA = "unidade-kds-http-outra"
AGORA = datetime.now(UTC) - timedelta(minutes=6)


def _pedido(
    *,
    pedido_id: str,
    item_id: str,
    tenant_id: str,
    unidade_id: str,
    nome: str,
    observacao: str | None,
) -> tuple[PedidoORM, ItemPedidoORM]:
    pedido = PedidoORM(
        id=pedido_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        origem="pdv",
        canal="pdv",
        status="enviado_producao",
        cliente_id=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"pedido-{pedido_id}",
        request_hash=f"{pedido_id:0<64}"[:64],
        subtotal=Decimal("30.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("30.00"),
    )
    item = ItemPedidoORM(
        id=item_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        pedido_id=pedido_id,
        ordem=1,
        produto_id=f"produto-{item_id}",
        nome_produto=nome,
        quantidade=1,
        preco_unitario=Decimal("30.00"),
        subtotal=Decimal("30.00"),
        observacao=observacao,
        ficha_versao="v1",
    )
    return pedido, item


def _setor(
    *,
    setor_id: str,
    tenant_id: str,
    unidade_id: str,
    codigo: str,
    nome: str,
    ordem: int,
    sla_segundos: int,
) -> SetorProducaoORM:
    return SetorProducaoORM(
        id=setor_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        codigo=codigo,
        nome=nome,
        ordem=ordem,
        sla_segundos=sla_segundos,
        ativo=True,
        criado_em=AGORA,
        atualizado_em=AGORA,
    )


def _producao(
    *,
    producao_id: str,
    pedido_id: str,
    pedido_item_id: str,
    setor_id: str,
    tenant_id: str,
    unidade_id: str,
    status: str,
    prioridade: int,
) -> ProducaoItemORM:
    return ProducaoItemORM(
        id=producao_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        pedido_id=pedido_id,
        pedido_item_id=pedido_item_id,
        setor_id=setor_id,
        status=status,
        prioridade=prioridade,
        quantidade=Decimal("1.0000"),
        tentativa=1,
        versao=1,
        criado_em=AGORA,
        atualizado_em=AGORA,
        aceita_em=AGORA if status == "aceita" else None,
        iniciada_em=None,
        pausa_iniciada_em=None,
        pronta_em=None,
        retirada_em=None,
        responsavel_id=None,
        pausa_acumulada_segundos=0,
        idempotency_key=f"route-{producao_id}",
        request_hash=f"{producao_id:0<64}"[:64],
    )


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="cozinha-kds@example.com",
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE,
            papeis=(Papel.COZINHA,),
        )

        quente_pedido, quente_item = _pedido(
            pedido_id="pedido-quente",
            item_id="item-quente",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome="X-Bacon",
            observacao="SEM CEBOLA",
        )
        bar_pedido, bar_item = _pedido(
            pedido_id="pedido-bar",
            item_id="item-bar",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            nome="Suco",
            observacao=None,
        )
        outro_pedido, outro_item = _pedido(
            pedido_id="pedido-outro",
            item_id="item-outro",
            tenant_id=TENANT_OUTRO,
            unidade_id=UNIDADE_OUTRA,
            nome="Pedido externo",
            observacao="NÃO VAZAR",
        )

        session.add_all(
            [
                quente_pedido,
                quente_item,
                bar_pedido,
                bar_item,
                outro_pedido,
                outro_item,
                _setor(
                    setor_id="setor-quente",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    codigo="quente",
                    nome="Cozinha Quente",
                    ordem=1,
                    sla_segundos=600,
                ),
                _setor(
                    setor_id="setor-bar",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    codigo="bar",
                    nome="Bar",
                    ordem=2,
                    sla_segundos=300,
                ),
                _setor(
                    setor_id="setor-outro",
                    tenant_id=TENANT_OUTRO,
                    unidade_id=UNIDADE_OUTRA,
                    codigo="outro",
                    nome="Setor externo",
                    ordem=1,
                    sla_segundos=300,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                _producao(
                    producao_id="prod-quente",
                    pedido_id="pedido-quente",
                    pedido_item_id="item-quente",
                    setor_id="setor-quente",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    status="aceita",
                    prioridade=5,
                ),
                _producao(
                    producao_id="prod-bar",
                    pedido_id="pedido-bar",
                    pedido_item_id="item-bar",
                    setor_id="setor-bar",
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    status="aguardando",
                    prioridade=1,
                ),
                _producao(
                    producao_id="prod-outro",
                    pedido_id="pedido-outro",
                    pedido_item_id="item-outro",
                    setor_id="setor-outro",
                    tenant_id=TENANT_OUTRO,
                    unidade_id=UNIDADE_OUTRA,
                    status="aguardando",
                    prioridade=99,
                ),
            ]
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


def _headers(key: str = "kds-http-contract-key") -> dict[str, str]:
    auth = base64.b64encode(
        f"cozinha-kds@example.com:{SENHA}".encode()
    ).decode()
    return {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE,
        "Idempotency-Key": key,
        "X-Correlation-ID": "corr-kds-http-contract",
    }


def _payload(
    *,
    destino: str,
    versao_esperada: int,
    producao_id: str = "prod-quente",
    motivo: str | None = None,
) -> dict[str, object]:
    return {
        "producao_id": producao_id,
        "destino": destino,
        "versao_esperada": versao_esperada,
        "motivo": motivo,
    }


def test_setores_e_fila_respeitam_tenant_e_filtro_de_setor() -> None:
    _, _, client = _infra()

    setores = client.get("/v1/kds/setores", headers=_headers())
    fila = client.get("/v1/kds/fila", headers=_headers())
    quente = client.get(
        "/v1/kds/fila",
        headers=_headers(),
        params={"setor_id": "setor-quente"},
    )

    assert setores.status_code == 200
    assert [item["setor_id"] for item in setores.json()["setores"]] == [
        "setor-quente",
        "setor-bar",
    ]

    assert fila.status_code == 200
    assert [ticket["producao_id"] for ticket in fila.json()["tickets"]] == [
        "prod-quente",
        "prod-bar",
    ]
    assert "prod-outro" not in {
        ticket["producao_id"] for ticket in fila.json()["tickets"]
    }

    assert quente.status_code == 200
    assert len(quente.json()["tickets"]) == 1
    ticket = quente.json()["tickets"][0]
    assert ticket["producao_id"] == "prod-quente"
    assert ticket["pedido_id"] == "pedido-quente"
    assert ticket["setor_id"] == "setor-quente"
    assert ticket["versao"] == 1
    assert ticket["sla"]["decorrido_segundos"] >= 0
    assert ticket["itens"] == [
        {
            "pedido_item_id": "item-quente",
            "nome": "X-Bacon",
            "quantidade": 1,
            "observacoes": "SEM CEBOLA",
        }
    ]


def test_transicao_http_avanca_em_preparo_e_pronta() -> None:
    _, _, client = _infra()

    iniciado = client.post(
        "/v1/kds/transicionar",
        headers=_headers("kds-start-key"),
        json=_payload(destino="em_preparo", versao_esperada=1),
    )
    pronto = client.post(
        "/v1/kds/transicionar",
        headers=_headers("kds-ready-key"),
        json=_payload(destino="pronta", versao_esperada=2),
    )

    assert iniciado.status_code == 200
    assert iniciado.json()["status"] == "em_preparo"
    assert iniciado.json()["versao"] == 2
    assert iniciado.json()["pedido_status"] == "em_preparo"
    assert iniciado.json()["idempotente"] is False

    assert pronto.status_code == 200
    assert pronto.json()["status"] == "pronta"
    assert pronto.json()["versao"] == 3
    assert pronto.json()["pedido_status"] == "pronto"
    assert pronto.json()["idempotente"] is False


def test_transicao_http_rejeita_versao_defasada_com_409() -> None:
    _, _, client = _infra()

    response = client.post(
        "/v1/kds/transicionar",
        headers=_headers("kds-stale-key"),
        json=_payload(destino="em_preparo", versao_esperada=2),
    )

    assert response.status_code == 409
    assert response.json() == {"erro": "producao_concorrente"}


def test_transicao_http_replay_idempotente_retorna_200() -> None:
    _, _, client = _infra()
    headers = _headers("kds-replay-key")
    payload = _payload(destino="em_preparo", versao_esperada=1)

    primeiro = client.post("/v1/kds/transicionar", headers=headers, json=payload)
    replay = client.post("/v1/kds/transicionar", headers=headers, json=payload)

    assert primeiro.status_code == 200
    assert primeiro.json()["idempotente"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotente"] is True
    assert replay.json()["producao_id"] == primeiro.json()["producao_id"]
    assert replay.json()["status"] == primeiro.json()["status"]
    assert replay.json()["versao"] == primeiro.json()["versao"]


def test_fila_setor_inexistente_retorna_404_e_payload_invalido_422() -> None:
    _, _, client = _infra()

    setor_inexistente = client.get(
        "/v1/kds/fila",
        headers=_headers(),
        params={"setor_id": "setor-outro"},
    )
    payload_invalido = client.post(
        "/v1/kds/transicionar",
        headers=_headers("kds-invalid-key"),
        json={"producao_id": "prod-quente", "destino": "em_preparo"},
    )

    assert setor_inexistente.status_code == 404
    assert setor_inexistente.json() == {"erro": "setor_indisponivel"}
    assert payload_invalido.status_code == 422
