from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "admin-dashboard-session-secret-0123456789"
SENHA = "Senha-Segura-Dashboard-123"
TENANT = "tenant-dashboard-http"
UNIDADE_A = "unidade-dashboard-a"
UNIDADE_B = "unidade-dashboard-b"
ADMIN_EMAIL = "admin-dashboard@example.com"
COZINHA_EMAIL = "cozinha-dashboard@example.com"


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
        repositorio = RepositorioIdentidadesSQLAlchemy(session)
        repositorio.criar_usuario(
            usuario_id="usuario-admin-dashboard",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        repositorio.criar_usuario(
            usuario_id="usuario-cozinha-dashboard",
            email=COZINHA_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.COZINHA,),
            unidades_permitidas=(UNIDADE_A,),
        )
        session.commit()
    app = build_frontend_http_app(
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


def _login(client: TestClient, email: str = ADMIN_EMAIL) -> None:
    response = client.post("/v1/auth/login", json={"email": email, "senha": SENHA})
    assert response.status_code == 200


def _painel():
    return SimpleNamespace(
        tenant_id=TENANT,
        unidades=(UNIDADE_A,),
        financeiro=SimpleNamespace(
            vendas_reconhecidas=Decimal("150.00"),
            quantidade_vendas=3,
            ticket_medio=Decimal("50.00"),
            pagamentos_pagos=Decimal("130.00"),
            pagamentos_pendentes=Decimal("20.00"),
            pagamentos_estornados=Decimal("5.00"),
            recebido_dinheiro=Decimal("70.00"),
            cmv_estimado_atual=Decimal("60.00"),
            margem_estimada_atual=Decimal("90.00"),
            cobertura_cmv_itens_pct=Decimal("75.0"),
        ),
        operacional=SimpleNamespace(
            pedidos=4,
            estoque_fisico_total=Decimal("20.000"),
            estoque_reservado_total=Decimal("3.000"),
            entregas_por_status=(("aguardando_producao", 2),),
            integracoes_configuradas=3,
            integracoes_homologadas=2,
            usuarios_ativos=5,
        ),
    )


def test_painel_executivo_exige_sessao_e_permissoes(monkeypatch) -> None:
    client = _infra(monkeypatch)

    sem_sessao = client.get("/v1/admin/painel-executivo")
    _login(client, COZINHA_EMAIL)
    sem_permissao = client.get("/v1/admin/painel-executivo")

    assert sem_sessao.status_code == 401
    assert sem_sessao.json() == {"erro": "credenciais_invalidas"}
    assert sem_permissao.status_code == 403
    assert sem_permissao.json() == {"erro": "administracao_sem_acesso"}


def test_painel_executivo_reutiliza_application_e_escopo_ativo(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    chamadas = []

    class AplicacaoFake:
        def __init__(self, session_factory) -> None:
            self.session_factory = session_factory

        def painel_executivo(self, *, contexto, unidades):
            chamadas.append((contexto, unidades))
            return _painel()

    monkeypatch.setattr(
        "http_api.admin_dashboard.AplicacaoAdministracaoProprietarioV1",
        AplicacaoFake,
    )
    _login(client)

    response = client.get(
        "/v1/admin/painel-executivo",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    assert chamadas[0][0].tenant_id == TENANT
    assert chamadas[0][0].unidade_id == UNIDADE_A
    assert chamadas[0][1] == (UNIDADE_A,)
    assert response.json() == {
        "tenant_id": TENANT,
        "unidades": [UNIDADE_A],
        "financeiro": {
            "vendas_reconhecidas": "150.00",
            "quantidade_vendas": 3,
            "ticket_medio": "50.00",
            "pagamentos_pagos": "130.00",
            "pagamentos_pendentes": "20.00",
            "pagamentos_estornados": "5.00",
            "recebido_dinheiro": "70.00",
            "cmv_estimado_atual": "60.00",
            "margem_estimada_atual": "90.00",
            "cobertura_cmv_itens_pct": "75.0",
        },
        "operacional": {
            "pedidos": 4,
            "estoque_fisico_total": "20.000",
            "estoque_reservado_total": "3.000",
            "entregas_por_status": [
                {"status": "aguardando_producao", "quantidade": 2}
            ],
            "integracoes_configuradas": 3,
            "integracoes_homologadas": 2,
            "usuarios_ativos": 5,
        },
    }


def test_painel_executivo_encaminha_multiplas_unidades_ao_boundary(
    monkeypatch,
) -> None:
    client = _infra(monkeypatch)
    unidades_recebidas = []

    class AplicacaoFake:
        def __init__(self, session_factory) -> None:
            self.session_factory = session_factory

        def painel_executivo(self, *, contexto, unidades):
            unidades_recebidas.append(unidades)
            return _painel()

    monkeypatch.setattr(
        "http_api.admin_dashboard.AplicacaoAdministracaoProprietarioV1",
        AplicacaoFake,
    )
    _login(client)

    response = client.get(
        "/v1/admin/painel-executivo"
        f"?unidade_id={UNIDADE_A}&unidade_id={UNIDADE_B}"
    )

    assert response.status_code == 200
    assert unidades_recebidas == [(UNIDADE_A, UNIDADE_B)]
