"""Regressão: chamadas externas do Gerente IA não retêm conexões de negócio."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import application.ai_router_runtime as router_runtime
import application.gerente_ia_web as web
from core.ai_router import CapabilityIA, RespostaModeloIA, RotaIA, SolicitacaoIA
from core.seguranca.permissoes import Papel
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from migrations.runner import run_migrations


def _cenario(tmp_path, monkeypatch, *, revoke_during_llm: bool = False):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'gerente_ai_pool.db'}",
        pool_size=3,
        max_overflow=0,
        pool_timeout=0.5,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        repo = RepositorioIdentidadesSQLAlchemy(session)
        user = repo.criar_usuario(
            usuario_id="usuario-pool",
            email="usuario-pool@example.com",
            password="Senha-Forte-Gerente-Pool-123",
            tenant_id="tenant-pool",
            unidade_padrao_id="unidade-pool",
            papeis=(Papel.GERENTE,),
            unidades_permitidas=("unidade-pool",),
        )
        session.commit()
        user_id = user.usuario_id

    invoked = {"planner": 0, "tool": 0, "checkedout": -1}

    class IdentityFake:
        def __init__(self, session):
            self.session = session

        def obter(self, *, contexto):
            self.session.execute(text("SELECT 1"))
            return SimpleNamespace(nome_publico="Gerente")

    class RuntimeFake:
        def __init__(self, session):
            self.identidade_assistente = IdentityFake(session)
            self.session = session

        def executar_tool(self, *, contexto, chamada):
            invoked["tool"] += 1
            self.session.execute(text("SELECT 1"))
            return "ok"

    class RouterFake:
        def executar(self, solicitacao):
            invoked["planner"] += 1
            invoked["checkedout"] = engine.pool.checkedout()
            if revoke_during_llm:
                with factory() as session:
                    RepositorioIdentidadesSQLAlchemy(session).definir_papeis(
                        usuario_id=user_id, papeis=(Papel.GARCOM,)
                    )
                    session.commit()
            return RespostaModeloIA(
                conteudo={"tool": "consultar_atrasos", "argumentos": {}},
            )

    monkeypatch.setattr(
        web,
        "compor_runtime_gerente_ia",
        lambda *, session, secret_store=None: RuntimeFake(session),
    )
    monkeypatch.setattr(
        web,
        "construir_ai_model_router",
        lambda **kwargs: RouterFake(),
    )

    with factory() as session:
        identity = RepositorioIdentidadesSQLAlchemy(session).obter_por_id(
            usuario_id=user_id
        )
        assert identity is not None
        contexto = identity.contexto(origem="regression")
    return engine, web.AplicacaoGerenteIAWebV1(factory), contexto, invoked


def test_perguntar_releases_pool_before_llm_and_recovers_for_tool(
    tmp_path, monkeypatch
):
    engine, app, context, invoked = _cenario(tmp_path, monkeypatch)
    try:
        identidade, chamada, resultado = app.perguntar(
            contexto=context, pergunta="Quantos pedidos atrasados?"
        )
        assert identidade.nome_publico == "Gerente"
        assert chamada.tool.value == "consultar_atrasos"
        assert resultado == "ok"
        assert invoked == {"planner": 1, "tool": 1, "checkedout": 0}
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_role_revocation_during_llm_denies_tool_without_effect(
    tmp_path, monkeypatch
):
    engine, app, context, invoked = _cenario(
        tmp_path, monkeypatch, revoke_during_llm=True
    )
    try:
        with pytest.raises(PermissionError, match="permissao_revogada"):
            app.perguntar(
                contexto=context, pergunta="Quantos pedidos atrasados?"
            )
        assert invoked == {"planner": 1, "tool": 0, "checkedout": 0}
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


def test_real_provider_executor_releases_config_connection_before_network(
    tmp_path, monkeypatch
):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'external_provider.db'}",
        pool_size=2, max_overflow=0, pool_timeout=0.5
    )
    factory = sessionmaker(bind=engine)
    events = []

    class FakeStore:
        def for_session(self, session):
            events.append("vault_rebound")
            return self

    class FakeAdapter:
        def gerar(self, conteudo):
            assert engine.pool.checkedout() == 0
            events.append("network_without_db_checkout")
            return "ok"

    class FakeAdapterFactory:
        def __init__(self, *, session, secret_store):
            assert engine.pool.checkedout() == 0
            self.session = session

        def openai(self, *, contexto, configuracao_id, gateway):
            self.session.execute(text("SELECT 1"))
            assert engine.pool.checkedout() == 1
            events.append("credentials_read")
            return FakeAdapter()

    monkeypatch.setattr(
        router_runtime, "FabricaAdaptersExternos", FakeAdapterFactory
    )
    with factory() as db:
        executor = router_runtime.ExecutorControlPlaneIA(
            session=db,
            contexto=SimpleNamespace(tenant_id="tenant", unidade_id="unit"),
            secret_store=FakeStore(),
            session_factory=factory,
        )
        route = RotaIA(
            configuracao_id="ia.generativa--openai",
            provider="openai",
            model="modelo-teste",
            capability=CapabilityIA.TOOL_PLANNING,
            prioridade=100,
            price_snapshot_id="test",
        )
        request = SolicitacaoIA(
            tenant_id="tenant",
            unidade_id="unit",
            request_id="req-1",
            correlation_id="corr-1",
            capability=CapabilityIA.TOOL_PLANNING,
            conteudo={"user": "Teste"},
        )
        answer = executor.executar(rota=route, solicitacao=request)
        assert answer.conteudo == "ok"
        assert engine.pool.checkedout() == 0
    assert events == [
        "vault_rebound", "credentials_read", "network_without_db_checkout"
    ]
    engine.dispose()
