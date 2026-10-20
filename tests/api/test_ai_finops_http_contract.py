from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.ai_finops import AIFinOpsBucket
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.permissoes import Papel
from http_api.frontend_app import build_frontend_http_app
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "ai-finops-session-secret-0123456789-abcdef"
SENHA = "Senha-Segura-AI-FinOps-123"
TENANT = "tenant-ai-finops-http"
UNIDADE_A = "unidade-ai-finops-a"
UNIDADE_B = "unidade-ai-finops-b"
ADMIN_EMAIL = "admin-ai-finops@example.com"
COZINHA_EMAIL = "cozinha-ai-finops@example.com"


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
            usuario_id="usuario-admin-ai-finops",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A, UNIDADE_B),
        )
        repositorio.criar_usuario(
            usuario_id="usuario-cozinha-ai-finops",
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


def _bucket() -> AIFinOpsBucket:
    return AIFinOpsBucket(
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
        bucket_date=date(2026, 9, 8),
        provider="gemini",
        model="gemini-flash",
        capability="crm_resgate",
        outcome="success",
        moeda="USD",
        attempts=2,
        fallback_attempts=1,
        input_tokens=100,
        output_tokens=40,
        cached_tokens=20,
        latency_ms_total=300,
        latency_ms_max=200,
        cost_known_events=2,
        cost_unknown_events=0,
        cost_total=Decimal("0.25"),
    )


def test_ai_finops_exige_sessao_admin(monkeypatch) -> None:
    client = _infra(monkeypatch)
    caminho = "/v1/ai-finops/resumo?inicio=2026-09-01&fim=2026-09-09"

    sem_sessao = client.get(caminho)
    _login(client, COZINHA_EMAIL)
    sem_permissao = client.get(caminho)

    assert sem_sessao.status_code == 401
    assert sem_sessao.json() == {"erro": "credenciais_invalidas"}
    assert sem_permissao.status_code == 403
    assert sem_permissao.json() == {"erro": "administracao_sem_acesso"}


def test_ai_finops_preserva_periodo_e_escopo_da_sessao(monkeypatch) -> None:
    client = _infra(monkeypatch)
    chamadas = []

    class ReadModelFake:
        def __init__(self, session_factory) -> None:
            self.session_factory = session_factory

        def listar(self, **kwargs):
            chamadas.append(kwargs)
            return (_bucket(),)

    monkeypatch.setattr(
        "http_api.ai_finops.AIFinOpsSQLAlchemyReadModel",
        ReadModelFake,
    )
    _login(client)

    response = client.get(
        "/v1/ai-finops/resumo?inicio=2026-09-01&fim=2026-09-09",
        headers={"X-Tenant-ID": "tenant-spoof", "X-Unit-ID": UNIDADE_B},
    )

    assert response.status_code == 200
    assert chamadas == [
        {
            "tenant_id": TENANT,
            "unidade_id": UNIDADE_A,
            "inicio": date(2026, 9, 1),
            "fim": date(2026, 9, 9),
        }
    ]
    assert response.json() == {
        "tenant_id": TENANT,
        "unidade_id": UNIDADE_A,
        "inicio": "2026-09-01",
        "fim": "2026-09-09",
        "resumo": {
            "attempts": 2,
            "success_attempts": 2,
            "failure_attempts": 0,
            "fallback_attempts": 1,
            "input_tokens": 100,
            "output_tokens": 40,
            "cached_tokens": 20,
            "latency_ms_average": "150",
            "latency_ms_max": 200,
            "cost_known_events": 2,
            "cost_unknown_events": 0,
            "success_rate_pct": "100",
            "fallback_rate_pct": "50",
            "cost_coverage_pct": "100",
            "custos": [{"moeda": "USD", "valor": "0.25", "eventos": 2}],
            "mix": [
                {
                    "provider": "gemini",
                    "model": "gemini-flash",
                    "attempts": 2,
                }
            ],
        },
    }


def test_ai_finops_rejeita_periodo_invertido(monkeypatch) -> None:
    client = _infra(monkeypatch)
    _login(client)

    response = client.get(
        "/v1/ai-finops/resumo?inicio=2026-09-09&fim=2026-09-01"
    )

    assert response.status_code == 400
    assert response.json() == {"erro": "ai_finops.periodo_invalido"}
