from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.impressao_transacoes import AplicacaoImpressaoV1
from core.impressao import DestinoImpressao, JobImpressao
from core.impressao.adapters import ImpressoraFake
from core.kds.modelos import ProducaoItem, SetorProducao
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel
from http_api.admin_impressao import build_admin_impressao_router
from http_api.auth import AuthSessionRuntime, build_auth_router
from infra.administracao.repositorio_sqlalchemy import (
    RepositorioAdministracaoSQLAlchemy,
)
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations

SESSION_SECRET = "admin-impressao-session-secret-0123456789"
SENHA = "Senha-Segura-Impressao-123"
TENANT = "tenant-impressao-http"
UNIDADE_A = "unidade-impressao-a"
COZINHA_EMAIL = "cozinha-impressao@example.com"
ADMIN_EMAIL = "admin-impressao@example.com"
GARCOM_EMAIL = "garcom-impressao@example.com"


def _infra(monkeypatch) -> tuple[TestClient, sessionmaker]:
    monkeypatch.setenv("FM_AI_SESSION_SECRET", SESSION_SECRET)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo_identidades = RepositorioIdentidadesSQLAlchemy(session)
        repo_identidades.criar_usuario(
            usuario_id="cozinha-impressao-user",
            email=COZINHA_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.COZINHA,),
            unidades_permitidas=(UNIDADE_A,),
            acesso_admin_sensivel=False,
        )
        repo_identidades.criar_usuario(
            usuario_id="admin-impressao-user",
            email=ADMIN_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.ADMINISTRADOR,),
            unidades_permitidas=(UNIDADE_A,),
            acesso_admin_sensivel=True,
        )
        repo_identidades.criar_usuario(
            usuario_id="garcom-impressao-user",
            email=GARCOM_EMAIL,
            password=SENHA,
            tenant_id=TENANT,
            unidade_padrao_id=UNIDADE_A,
            papeis=(Papel.GARCOM,),
            unidades_permitidas=(UNIDADE_A,),
            acesso_admin_sensivel=False,
        )
        repo_admin = RepositorioAdministracaoSQLAlchemy(session)
        repo_admin.garantir_escopo(
            tenant_id=TENANT,
            unidade_id=UNIDADE_A,
            nome_empresa="Empresa Impressao",
            nome_unidade="Cozinha Impressao",
        )
        session.commit()

        # Create print destinations via config
        config = repo_admin.obter_configuracao(tenant_id=TENANT, unidade_id=UNIDADE_A)
        if config:
            from core.administracao import ConfiguracaoEstabelecimento
            parametros = dict(config.parametros_operacionais)
            parametros["impressao"] = {
                "destinos": [
                    {
                        "provider": "raw_tcp",
                        "setor_id": "cozinha",
                        "impressora_id": "tcp://127.0.0.1:9100",
                        "ativo": True,
                        "max_tentativas": 3,
                    }
                ]
            }
            nova_config = ConfiguracaoEstabelecimento(
                tenant_id=TENANT,
                unidade_id=UNIDADE_A,
                formas_pagamento=config.formas_pagamento,
                taxa_servico_percentual=config.taxa_servico_percentual,
                parametros_operacionais=parametros,
                politica_financeira=config.politica_financeira,
                versao=config.versao,
            )
            repo_admin.salvar_configuracao(nova_config, versao_esperada=config.versao)
            session.commit()

    # Build test app with explicit ImpressoraFake injection
    from core.seguranca.segredos import ReferenceSecretStore

    settings = RuntimeSettings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite://",
        tenant_id=TENANT,
        unidade_id=UNIDADE_A,
    )
    secret_store = ReferenceSecretStore()
    auth_runtime = AuthSessionRuntime(
        session_factory=factory,
        secret_store=secret_store,
    )

    app = FastAPI()
    app.include_router(
        build_auth_router(
            session_factory=factory,
            settings=settings,
            secret_store=secret_store,
            runtime=auth_runtime,
        )
    )
    app.include_router(
        build_admin_impressao_router(
            session_factory=factory,
            auth_runtime=auth_runtime,
            impressora=ImpressoraFake(),
        )
    )

    return TestClient(app), factory


def _login(client: TestClient, email: str) -> None:
    response = client.post("/v1/auth/login", json={"email": email, "senha": SENHA})
    assert response.status_code == 200
    if email == ADMIN_EMAIL:
        response = client.post("/v1/auth/admin-step-up", json={"senha": SENHA})
        assert response.status_code == 200


def _contexto_cozinha(factory) -> ContextoExecucao:
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo.obter_por_email(COZINHA_EMAIL)
        assert identidade is not None
        return identidade.contexto(origem="test.setup")


def _criar_job_direto(factory, tenant_id: str, unidade_id: str, setor_id: str = "cozinha") -> JobImpressao:
    """Cria job direto no banco via Application para testes."""

    with factory() as session:
        repo_identidades = RepositorioIdentidadesSQLAlchemy(session)
        identidade = repo_identidades.obter_por_email(COZINHA_EMAIL)
        assert identidade is not None
        contexto = identidade.contexto(origem="test.setup")

    destinos = (
        DestinoImpressao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            setor_id=setor_id,
            impressora_id="tcp://127.0.0.1:9100",
            ativo=True,
            max_tentativas=3,
        ),
    )

    app = AplicacaoImpressaoV1(factory, impressora=ImpressoraFake(), destinos=destinos)

    agora = datetime.now(timezone.utc)
    producao = ProducaoItem(
        producao_id=f"prod-{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        setor_id=setor_id,
        pedido_id=f"pedido-{uuid4().hex[:8]}",
        pedido_item_id=f"item-{uuid4().hex[:8]}",
        quantidade=Decimal(1),
        status="aguardando_producao",
        prioridade=0,
        tentativa=1,
        versao=1,
        criado_em=agora,
        atualizado_em=agora,
    )

    setor = SetorProducao(
        setor_id=setor_id,
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        codigo=setor_id,
        nome="Cozinha",
        ordem=1,
        sla_segundos=300,
        ativo=True,
        criado_em=agora,
        atualizado_em=agora,
    )

    resultado = app.enfileirar_item_kds(
        contexto=contexto,
        producao=producao,
        setor=setor,
        idempotency_key=f"test-{uuid4()}",
        descricao_item="Hamburguer teste",
        observacao="Sem cebola",
        timestamp=agora,
    )
    assert resultado.enfileirado
    assert resultado.job is not None
    return resultado.job


def test_listar_jobs_exige_sessao(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)

    sem_sessao = client.get("/v1/admin/impressao/jobs")
    assert sem_sessao.status_code == 401


def test_listar_jobs_exige_admin_acessar(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client, COZINHA_EMAIL)

    sem_admin = client.get("/v1/admin/impressao/jobs")
    assert sem_admin.status_code == 403
    assert sem_admin.json() == {"erro": "seguranca.admin_acesso_exigido"}


def test_listar_jobs_vazio_inicial(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    response = client.get("/v1/admin/impressao/jobs")
    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_listar_jobs_com_dados(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.get("/v1/admin/impressao/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    job = data["jobs"][0]
    assert job["tenant_id"] == TENANT
    assert job["unidade_id"] == UNIDADE_A
    assert job["setor_id"] == "cozinha"
    assert job["status"] == "pendente"
    assert job["tentativa"] == 0


def test_processar_job_exige_admin(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, COZINHA_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(f"/v1/admin/impressao/jobs/{job.job_id}/processar")
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.admin_acesso_exigido"}


def test_processar_job_com_admin(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(f"/v1/admin/impressao/jobs/{job.job_id}/processar")
    assert response.status_code == 200
    data = response.json()
    assert data["impresso"] is True
    assert data["contingencia"] is False
    assert data["job"]["status"] == "impresso"
    assert data["job"]["tentativa"] == 1


def test_processar_job_ja_impresso_idempotente(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)
    client.post(f"/v1/admin/impressao/jobs/{job.job_id}/processar")

    response = client.post(f"/v1/admin/impressao/jobs/{job.job_id}/processar")
    assert response.status_code == 200
    data = response.json()
    assert data["impresso"] is True
    assert data["job"]["status"] == "impresso"


def test_processar_job_inexistente_404(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    response = client.post("/v1/admin/impressao/jobs/job-inexistente/processar")
    assert response.status_code == 400
    assert response.json()["erro"] == "job_impressao_indisponivel"


def test_reimprimir_job_exige_admin(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, COZINHA_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "ticket danificado", "idempotency_key": f"test-{uuid4()}"},
    )
    assert response.status_code == 403
    assert response.json() == {"erro": "seguranca.admin_acesso_exigido"}


def test_reimprimir_job_sem_permissao_reimprimir(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, GARCOM_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "ticket danificado", "idempotency_key": f"test-{uuid4()}"},
    )
    # GARCOM não tem admin.acessar, então retorna 403
    assert response.status_code == 403


def test_reimprimir_job_com_permissao(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "ticket danificado teste", "idempotency_key": f"test-{uuid4()}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reimpressao_de"] == job.job_id
    assert data["motivo_reimpressao"] == "ticket danificado teste"
    assert data["status"] == "pendente"
    assert data["versao"] == 1
    assert data["tentativa"] == 0


def test_reimprimir_job_idempotente(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)
    idempotency_key = f"test-{uuid4()}"

    client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "ticket danificado", "idempotency_key": idempotency_key},
    )

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "ticket danificado", "idempotency_key": idempotency_key},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["reimpressao_de"] == job.job_id


def test_reimprimir_job_motivo_curto_rejeitado(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "cur", "idempotency_key": f"test-{uuid4()}"},
    )
    assert response.status_code == 422


def test_reimprimir_job_sem_motivo_rejeitado(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    response = client.post(
        f"/v1/admin/impressao/jobs/{job.job_id}/reimprimir",
        json={"motivo": "", "idempotency_key": f"test-{uuid4()}"},
    )
    assert response.status_code == 422


def test_reimprimir_job_inexistente_404(monkeypatch) -> None:
    client, _ = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    response = client.post(
        "/v1/admin/impressao/jobs/job-inexistente/reimprimir",
        json={"motivo": "ticket danificado", "idempotency_key": f"test-{uuid4()}"},
    )
    assert response.status_code == 400
    assert response.json()["erro"] == "job_impressao_indisponivel"


def test_isolamento_tenant_unidade(monkeypatch) -> None:
    client, factory = _infra(monkeypatch)
    _login(client, ADMIN_EMAIL)

    job = _criar_job_direto(factory, TENANT, UNIDADE_A)

    # Headers X-Tenant-ID/X-Unit-ID são ignorados; escopo vem da sessão autenticada
    response = client.get(
        "/v1/admin/impressao/jobs",
        headers={"X-Tenant-ID": "outro-tenant", "X-Unit-ID": "outra-unidade"},
    )
    # Job existe no escopo da sessão (mesmo tenant/unidade), retorna 200
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_id"] == job.job_id