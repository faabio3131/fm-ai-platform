from __future__ import annotations

import base64
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.salao import RepositorioSalaoSQLAlchemy, ServicoSalao
from core.salao.modelos_orm import ComandaORM, EventoSalaoORM, MesaORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from http_api.app import build_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SENHA = "Senha-Segura-Salao-123"
TENANT = "tenant-salao-http"
UNIDADE = "unidade-salao-http"
OUTRO_TENANT = "tenant-salao-outro"
OUTRA_UNIDADE = "unidade-salao-outra"
MESA_ID = "mesa-http-01"


def _contexto_sistema(tenant_id: str, unidade_id: str) -> ContextoExecucao:
    return ContextoExecucao.sistema(
        identidade="fixture-salao-http",
        motivo="preparar contrato HTTP de Salao",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        correlation_id=f"fixture:{tenant_id}:{unidade_id}",
        solicitado_em=datetime.now(timezone.utc),
    )


def _cadastrar_mesa(
    factory,
    *,
    tenant_id: str,
    unidade_id: str,
    mesa_id: str,
    codigo: str,
) -> None:
    with factory() as session:
        ServicoSalao(
            RepositorioSalaoSQLAlchemy(session),
            agora=lambda: datetime.now(timezone.utc),
        ).cadastrar_mesa(
            _contexto_sistema(tenant_id, unidade_id),
            mesa_id=mesa_id,
            codigo=codigo,
            capacidade=4,
            idempotency_key=f"seed:{tenant_id}:{unidade_id}:{mesa_id}",
            nome=f"Mesa {codigo}",
        )
        session.commit()


def _infra():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    _cadastrar_mesa(
        factory,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        mesa_id=MESA_ID,
        codigo="01",
    )
    _cadastrar_mesa(
        factory,
        tenant_id=OUTRO_TENANT,
        unidade_id=OUTRA_UNIDADE,
        mesa_id="mesa-outro-tenant",
        codigo="99",
    )

    with factory() as session:
        RepositorioIdentidadesSQLAlchemy(session).criar_usuario(
            email="garcom-salao@example.com",
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
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
    )
    return engine, factory, TestClient(app)


def _headers(key: str | None = None) -> dict[str, str]:
    auth = base64.b64encode(
        f"garcom-salao@example.com:{SENHA}".encode()
    ).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "X-Tenant-ID": TENANT,
        "X-Unit-ID": UNIDADE,
        "X-Correlation-ID": "corr-salao-http-contract",
    }
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _abrir(client: TestClient, key: str):
    return client.post(
        "/v1/salao/comandas/abrir",
        headers=_headers(key),
        json={
            "mesa_id": MESA_ID,
            "responsavel_nome": "Garcom HTTP",
            "quantidade_pessoas": 3,
        },
    )


def test_mapa_salao_respeita_isolamento_tenant_unidade() -> None:
    _, _, client = _infra()

    response = client.get("/v1/salao/mapa", headers=_headers())

    assert response.status_code == 200
    assert response.json() == {
        "mesas": [
            {
                "id": MESA_ID,
                "numero": "01",
                "nome": "Mesa 01",
                "capacidade": 4,
                "status": "LIVRE",
            }
        ],
        "comandas": [],
    }


def test_abrir_comanda_muda_mesa_para_ocupada() -> None:
    engine, _, client = _infra()

    response = _abrir(client, "salao-open-001")

    assert response.status_code == 201
    body = response.json()
    assert body["idempotente"] is False
    assert body["comanda"]["mesa_id"] == MESA_ID
    assert body["comanda"]["status_comanda"] == "ABERTA"

    with Session(engine) as session:
        mesa = session.get(MesaORM, (MESA_ID, TENANT, UNIDADE))
        assert mesa is not None
        assert mesa.status == "ocupada"


def test_abrir_comanda_rejeita_mesa_ja_ocupada_com_409() -> None:
    _, _, client = _infra()

    primeira = _abrir(client, "salao-open-002-a")
    conflito = _abrir(client, "salao-open-002-b")

    assert primeira.status_code == 201
    assert conflito.status_code == 409
    assert conflito.json() == {"erro": "mesa_indisponivel"}


def test_solicitar_conta_transiciona_para_conta_solicitada() -> None:
    engine, _, client = _infra()
    abertura = _abrir(client, "salao-open-003")
    comanda_id = abertura.json()["comanda"]["id"]

    response = client.post(
        f"/v1/salao/comandas/{comanda_id}/solicitar-conta",
        headers=_headers("salao-conta-003"),
    )

    assert abertura.status_code == 201
    assert response.status_code == 200
    assert response.json()["comanda"]["status_comanda"] == "CONTA_SOLICITADA"

    with Session(engine) as session:
        comanda = session.get(ComandaORM, (comanda_id, TENANT, UNIDADE))
        assert comanda is not None
        assert comanda.status == "conta_solicitada"


def test_abrir_comanda_replay_idempotente_retorna_200_sem_duplicar() -> None:
    engine, _, client = _infra()
    key = "salao-open-replay-004"

    primeira = _abrir(client, key)
    replay = _abrir(client, key)

    assert primeira.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["idempotente"] is True
    assert replay.json()["comanda"]["id"] == primeira.json()["comanda"]["id"]

    with Session(engine) as session:
        comandas = session.scalar(select(func.count()).select_from(ComandaORM)) or 0
        eventos = (
            session.scalar(
                select(func.count())
                .select_from(EventoSalaoORM)
                .where(
                    EventoSalaoORM.tenant_id == TENANT,
                    EventoSalaoORM.unidade_id == UNIDADE,
                    EventoSalaoORM.idempotency_key == key,
                )
            )
            or 0
        )
        assert comandas == 1
        assert eventos == 1
