from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from application.ai_finops_dashboard import resumir_ai_finops
from core.ai_finops import AIFinOpsBucket
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.ai_finops_models import AIFinOpsDailyORM
from infra.ai_finops_read_model import AIFinOpsSQLAlchemyReadModel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "wp019-session-secret-0123456789-abcdef"
SENHA = "Senha-Segura-WP019-123"
TENANT = "tenant-wp019"
OUTRO_TENANT = "tenant-outro-wp019"
UNIDADE_A = "unidade-wp019-a"
UNIDADE_B = "unidade-wp019-b"
ADMIN_EMAIL = "admin-wp019@example.com"
LIMITADO_EMAIL = "limitado-wp019@example.com"


def _infra(monkeypatch):
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        repo.criar_usuario(
            usuario_id="admin-wp019",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        repo.criar_usuario(
            usuario_id="limitado-wp019",
            email=LIMITADO_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ATENDIMENTO,),
            unidades_permitidas=(UNIDADE_A,),
            acesso_admin_sensivel=True,
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
    return TestClient(app), factory


def _login(client: TestClient, email: str) -> None:
    response = client.post("/v1/auth/login", json={"email": email, "senha": SENHA})
    assert response.status_code == 200


def _row(
    *,
    aggregate_id: str,
    tenant_id: str = TENANT,
    unidade_id: str = UNIDADE_A,
    bucket_date: date = date(2026, 9, 8),
    provider: str = "gemini",
    model: str = "gemini-flash",
    outcome: str = "success",
    moeda: str = "USD",
    attempts: int = 2,
    fallback_attempts: int = 0,
    input_tokens: int = 100,
    output_tokens: int = 40,
    cached_tokens: int = 20,
    latency_ms_total: int = 300,
    latency_ms_max: int = 200,
    cost_known_events: int = 2,
    cost_unknown_events: int = 0,
    cost_total: Decimal = Decimal("0.25"),
) -> AIFinOpsDailyORM:
    return AIFinOpsDailyORM(
        aggregate_id=aggregate_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        bucket_date=bucket_date,
        provider=provider,
        model=model,
        capability="crm_resgate",
        outcome=outcome,
        moeda=moeda,
        attempts=attempts,
        fallback_attempts=fallback_attempts,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        latency_ms_total=latency_ms_total,
        latency_ms_max=latency_ms_max,
        cost_known_events=cost_known_events,
        cost_unknown_events=cost_unknown_events,
        cost_total=cost_total,
    )


def test_wp019_exige_admin_e_permissao_financeira(monkeypatch) -> None:
    client, _factory = _infra(monkeypatch)
    _login(client, LIMITADO_EMAIL)

    response = client.get(
        "/v1/ai-finops/resumo?inicio=2026-09-01&fim=2026-09-09"
    )

    assert response.status_code == 403
    assert response.json() == {
        "erro": "administracao_sem_permissao:financeiro.visualizar"
    }


def test_wp019_troca_de_unidade_governa_read_model_e_headers_nao_expandem_escopo(
    monkeypatch,
) -> None:
    client, _factory = _infra(monkeypatch)
    chamadas: list[dict[str, object]] = []

    class ReadModelFake:
        def __init__(self, session_factory) -> None:
            self.session_factory = session_factory

        def listar(self, **kwargs):
            chamadas.append(kwargs)
            return ()

    monkeypatch.setattr(
        "http_api.ai_finops.AIFinOpsSQLAlchemyReadModel",
        ReadModelFake,
    )
    _login(client, ADMIN_EMAIL)
    troca = client.post("/v1/auth/select-unit", json={"unidade_id": UNIDADE_B})
    assert troca.status_code == 200

    response = client.get(
        "/v1/ai-finops/resumo?inicio=2026-09-01&fim=2026-09-09",
        headers={"X-Tenant-ID": OUTRO_TENANT, "X-Unit-ID": UNIDADE_A},
    )

    assert response.status_code == 200
    assert response.json()["tenant_id"] == TENANT
    assert response.json()["unidade_id"] == UNIDADE_B
    assert chamadas == [
        {
            "tenant_id": TENANT,
            "unidade_id": UNIDADE_B,
            "inicio": date(2026, 9, 1),
            "fim": date(2026, 9, 9),
        }
    ]


def test_wp019_read_model_isola_tenant_unidade_periodo_e_nao_inventa_custo() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with Session(engine) as session:
        session.add_all(
            (
                _row(aggregate_id="alvo-known"),
                _row(
                    aggregate_id="alvo-unknown",
                    provider="openai",
                    model="gpt-x",
                    outcome="failure",
                    moeda="XXX",
                    attempts=1,
                    fallback_attempts=1,
                    input_tokens=50,
                    output_tokens=10,
                    cached_tokens=0,
                    latency_ms_total=120,
                    latency_ms_max=120,
                    cost_known_events=0,
                    cost_unknown_events=1,
                    cost_total=Decimal(0),
                ),
                _row(
                    aggregate_id="outra-unidade",
                    unidade_id=UNIDADE_B,
                    cost_total=Decimal("99"),
                ),
                _row(
                    aggregate_id="outro-tenant",
                    tenant_id=OUTRO_TENANT,
                    cost_total=Decimal("77"),
                ),
                _row(
                    aggregate_id="fora-periodo",
                    bucket_date=date(2026, 8, 31),
                    cost_total=Decimal("55"),
                ),
            )
        )
        session.commit()

    buckets = AIFinOpsSQLAlchemyReadModel(factory).listar(
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        inicio=date(2026, 9, 1),
        fim=date(2026, 9, 9),
    )
    assert len(buckets) == 2
    assert {(item.provider, item.moeda) for item in buckets} == {
        ("gemini", "USD"),
        ("openai", "XXX"),
    }

    resumo = resumir_ai_finops(buckets)
    assert resumo.attempts == 3
    assert resumo.success_attempts == 2
    assert resumo.failure_attempts == 1
    assert resumo.fallback_attempts == 1
    assert resumo.input_tokens == 150
    assert resumo.output_tokens == 50
    assert resumo.cached_tokens == 20
    assert resumo.latency_ms_average == Decimal(140)
    assert resumo.latency_ms_max == 200
    assert resumo.cost_known_events == 2
    assert resumo.cost_unknown_events == 1
    assert resumo.cost_coverage_pct == Decimal(200) / Decimal(3)
    assert [(item.moeda, item.valor, item.eventos) for item in resumo.custos] == [
        ("USD", Decimal("0.250000000000000000"), 2)
    ]
    assert [(item.provider, item.model, item.attempts) for item in resumo.mix] == [
        ("gemini", "gemini-flash", 2),
        ("openai", "gpt-x", 1),
    ]


def test_wp019_periodo_sem_eventos_retorna_resumo_neutro() -> None:
    resumo = resumir_ai_finops(())

    assert resumo.attempts == 0
    assert resumo.success_attempts == 0
    assert resumo.failure_attempts == 0
    assert resumo.fallback_attempts == 0
    assert resumo.input_tokens == 0
    assert resumo.output_tokens == 0
    assert resumo.cached_tokens == 0
    assert resumo.latency_ms_average == Decimal(0)
    assert resumo.latency_ms_max == 0
    assert resumo.cost_known_events == 0
    assert resumo.cost_unknown_events == 0
    assert resumo.success_rate_pct == Decimal(0)
    assert resumo.fallback_rate_pct == Decimal(0)
    assert resumo.cost_coverage_pct == Decimal(0)
    assert resumo.custos == ()
    assert resumo.mix == ()


def test_wp019_bucket_sem_preco_nao_pode_carregar_custo_inventado() -> None:
    bucket = AIFinOpsBucket(
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        bucket_date=date(2026, 9, 8),
        provider="provider-sem-preco",
        model="modelo-sem-preco",
        capability="assistente",
        outcome="success",
        moeda="XXX",
        attempts=1,
        fallback_attempts=0,
        input_tokens=10,
        output_tokens=5,
        cached_tokens=0,
        latency_ms_total=50,
        latency_ms_max=50,
        cost_known_events=0,
        cost_unknown_events=1,
        cost_total=Decimal(0),
    )

    resumo = resumir_ai_finops((bucket,))

    assert resumo.cost_known_events == 0
    assert resumo.cost_unknown_events == 1
    assert resumo.cost_coverage_pct == Decimal(0)
    assert resumo.custos == ()
