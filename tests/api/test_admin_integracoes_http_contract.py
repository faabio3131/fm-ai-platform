"""Testes de contrato HTTP para admin_integracoes (WP-026)."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.integracoes.modelos import (
    AmbienteIntegracao,
    ConfiguracaoServicoExterno,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from http_api.admin_integracoes import build_admin_integracoes_router
from http_api.auth import AuthSessionRuntime
from infra.integracoes.modelos_orm import IntegrationConfigBase
from infra.seguranca.modelos_orm import SecurityBase
from infra.seguranca.segredos_orm import SecretVaultBase

TENANT = "tenant-wp026"
UNIDADE = "unidade-wp026"
USUARIO = "admin-wp026"
AGORA = datetime(2026, 9, 13, 12, 0, 0, tzinfo=UTC)


def _contexto_admin() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id=USUARIO,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-wp026",
        solicitado_em=AGORA,
        origem="tests.admin_integracoes",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _contexto_sem_admin() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="gerente-wp026",
        papeis=frozenset({Papel.GERENTE}),
        permissoes=frozenset(
            p for p in Permissao if p not in {Permissao.ADMIN_ACESSAR, Permissao.PERMISSAO_GERENCIAR}
        ),
        correlation_id="corr-wp026-gerente",
        solicitado_em=AGORA,
        origem="tests.admin_integracoes",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _engine_memoria():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SecurityBase.metadata.create_all(engine)
    SecretVaultBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    return engine


@pytest.fixture
def app_com_mocks() -> FastAPI:
    engine = _engine_memoria()
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with patch("http_api.auth.AuthSessionRuntime") as mock_auth_runtime_class, patch(
        "http_api.admin_integracoes.AplicacaoIntegracoesAdminV1"
    ) as mock_app_class, patch(
        "http_api.admin_integracoes.ServicoConfiguracoesExternas"
    ) as mock_service_class, patch(
        "http_api.admin_integracoes.EncryptedSQLAlchemySecretStore"
    ) as mock_vault_class, patch(
        "http_api.admin_integracoes.RepositorioConfiguracoesExternasSQLAlchemy"
    ) as mock_repo_class, patch(
        "http_api.admin_integracoes.ProntidaoCredenciaisSQLAlchemy"
    ) as mock_readiness_class, patch(
        "http_api.admin_integracoes.RepositorioAuditoriaSQLAlchemy"
    ) as mock_audit_class, patch(
        "http_api.admin_integracoes.executar_healthcheck_gemini"
    ) as mock_hc_gemini, patch(
        "http_api.admin_integracoes.executar_healthcheck_google_maps"
    ) as mock_hc_maps, patch(
        "http_api.admin_integracoes.executar_healthcheck_mercado_pago"
    ) as mock_hc_mp, patch(
        "http_api.admin_integracoes.executar_healthcheck_meta"
    ) as mock_hc_meta:

        mock_auth = MagicMock(spec=AuthSessionRuntime)
        mock_auth.resolver_identidade = MagicMock(return_value=None)
        mock_auth.admin_status = MagicMock(return_value=(None, False, None))
        mock_auth_runtime_class.return_value = mock_auth

        mock_app = MagicMock()
        mock_app_class.return_value = mock_app

        mock_service = MagicMock()
        mock_service.listar = MagicMock(return_value=())
        mock_service.obter = MagicMock()
        mock_service.avaliar = MagicMock()
        mock_service_class.return_value = mock_service

        mock_vault = MagicMock()
        mock_vault_class.return_value = mock_vault

        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo

        mock_readiness = MagicMock()
        mock_readiness_class.return_value = mock_readiness

        mock_audit = MagicMock()
        mock_audit_class.return_value = mock_audit

        mock_hc_gemini.return_value = MagicMock(evidencia_ref="healthcheck://gemini/test", model="gemini-test")
        mock_hc_maps.return_value = MagicMock(
            evidencia_ref="healthcheck://google-maps-server/test",
            endereco_origem="A",
            endereco_destino="B",
            distancia_metros=1000,
            duracao_segundos=60,
            browser_key_presente=True,
        )
        mock_hc_mp.return_value = MagicMock(evidencia_ref="healthcheck://mercado-pago-access/test", credencial_valida=True)
        mock_hc_meta.return_value = MagicMock(
            evidencia_ref="healthcheck://meta-access/test", servico="mensageria.whatsapp", recurso_id="123", rotulo="Test"
        )

        app = FastAPI()
        app.include_router(
            build_admin_integracoes_router(
                session_factory=factory,
                auth_runtime=mock_auth,
                master_key="test-master-key",
            )
        )
        yield app, {
            "engine": engine,
            "factory": factory,
            "auth": mock_auth,
            "app": mock_app,
            "service": mock_service,
            "vault": mock_vault,
            "repo": mock_repo,
            "readiness": mock_readiness,
            "audit": mock_audit,
            "hc_gemini": mock_hc_gemini,
            "hc_maps": mock_hc_maps,
            "hc_mp": mock_hc_mp,
            "hc_meta": mock_hc_meta,
        }


def _identidade_admin():
    from core.seguranca.autenticacao import IdentidadeUsuario
    return IdentidadeUsuario(
        usuario_id=USUARIO,
        email="admin@test.com",
        senha_hash="hash",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        unidades_permitidas=frozenset({UNIDADE}),
        ativo=True,
        acesso_admin_sensivel=True,
    )


def _identidade_gerente():
    from core.seguranca.autenticacao import IdentidadeUsuario
    return IdentidadeUsuario(
        usuario_id="gerente-wp026",
        email="gerente@test.com",
        senha_hash="hash",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        papeis=frozenset({Papel.GERENTE}),
        unidades_permitidas=frozenset({UNIDADE}),
        ativo=True,
        acesso_admin_sensivel=False,
    )


def test_get_sem_sessao_retorna_401(app_com_mocks):
    app, _ = app_com_mocks
    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 401


def test_get_sem_admin_acessar_retorna_403(app_com_mocks):
    app, mocks = app_com_mocks
    mocks["auth"].resolver_identidade.return_value = _identidade_gerente()
    mocks["auth"].admin_status.return_value = (_identidade_gerente(), False, None)
    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 403


def test_get_sem_integracao_gerenciar_retorna_403(app_com_mocks):
    app, mocks = app_com_mocks
    from core.seguranca.autenticacao import IdentidadeUsuario
    ident = IdentidadeUsuario(
        usuario_id="user-sem-permissao",
        email="user@test.com",
        senha_hash="hash",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        papeis=frozenset({Papel.CAIXA}),
        unidades_permitidas=frozenset({UNIDADE}),
        ativo=True,
        acesso_admin_sensivel=True,
    )
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)
    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 403


def test_get_nao_exige_step_up(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)

    mocks["service"].listar.return_value = ()

    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 200
    assert "integracoes" in resp.json()


def test_put_exige_step_up(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, False, None)

    client = TestClient(app)
    resp = client.put(
        "/v1/admin/integracoes/ia.generativa--gemini",
        json={
            "servico": "ia.generativa",
            "provedor": "gemini",
            "conta_externa": "principal",
            "ambiente": "sandbox",
            "parametros": [{"nome": "model", "valor": "gemini-test"}],
            "credenciais": [{"papel": "api_key", "valor": "secret"}],
            "habilitada": True,
            "versao": 0,
        },
    )
    assert resp.status_code == 403


def test_healthcheck_exige_step_up(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, False, None)

    mocks["service"].obter.return_value = MagicMock(
        configuracao_id="ia.generativa--gemini",
        servico="ia.generativa",
        provedor="gemini",
        credenciais={"api_key": "purpose"},
    )

    client = TestClient(app)
    resp = client.post("/v1/admin/integracoes/ia.generativa--gemini/healthcheck")
    assert resp.status_code == 403


def test_homologar_exige_step_up(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, False, None)

    client = TestClient(app)
    resp = client.post(
        "/v1/admin/integracoes/ia.generativa--gemini/homologar",
        json={"evidencia_ref": "healthcheck://gemini/test"},
    )
    assert resp.status_code == 403


def test_homologar_nao_admin_proibido(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_gerente()
    ident = type(ident)(
        usuario_id=ident.usuario_id,
        email=ident.email,
        senha_hash=ident.senha_hash,
        tenant_id=ident.tenant_id,
        unidade_id=ident.unidade_id,
        papeis=frozenset({Papel.GERENTE}),
        unidades_permitidas=ident.unidades_permitidas,
        ativo=ident.ativo,
        acesso_admin_sensivel=True,
    )
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)

    client = TestClient(app)
    resp = client.post(
        "/v1/admin/integracoes/ia.generativa--gemini/homologar",
        json={"evidencia_ref": "healthcheck://gemini/test"},
    )
    assert resp.status_code == 403


def test_tenant_unidade_da_sessao(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)
    mocks["service"].listar.return_value = ()

    client = TestClient(app)
    client.headers.update({"X-Tenant-ID": "outro-tenant", "X-Unit-ID": "outra-unidade"})
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 200

    called_context = mocks["service"].listar.call_args[1]["contexto"]
    assert called_context.tenant_id == TENANT
    assert called_context.unidade_id == UNIDADE


def test_spoof_header_nao_altera_escopo(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)
    mocks["service"].listar.return_value = ()

    client = TestClient(app)
    client.headers.update({"X-Tenant-ID": "spoof-tenant", "X-Unit-ID": "spoof-unidade"})
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 200

    called_context = mocks["service"].listar.call_args[1]["contexto"]
    assert called_context.tenant_id == TENANT
    assert called_context.unidade_id == UNIDADE


def test_get_nunca_retorna_segredo(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].listar.return_value = (config,)
    mocks["service"].avaliar.return_value = MagicMock(
        estado=EstadoProntidaoServico.CONFIGURADO,
        faltam_parametros=(),
        faltam_finalidades=(),
        faltam_credenciais=(),
        pronto=False,
    )

    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 200
    data = resp.json()
    integracao = data["integracoes"][0]
    assert integracao["configuracao"] is not None
    assert "credenciais_estado" in integracao["configuracao"]
    assert integracao["configuracao"]["credenciais_estado"]["api_key"] is True
    assert "parametros" in integracao["configuracao"]
    assert "model" in integracao["configuracao"]["parametros"]


def test_put_credencial_vazia_preserva_existente(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config_existente = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config_existente

    mocks["app"].salvar_configuracao.return_value = (
        ConfiguracaoServicoExterno(
            configuracao_id="ia.generativa--gemini",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            servico="ia.generativa",
            provedor="gemini",
            conta_externa="principal",
            ambiente=AmbienteIntegracao.SANDBOX,
            parametros_publicos=(("model", "gemini-test"),),
            finalidades_credenciais=(("api_key", "purpose_1"),),
            habilitada=True,
            homologada=False,
            evidencia_homologacao_ref=None,
            versao=2,
            atualizado_por=USUARIO,
            correlation_id="corr",
            atualizado_em=AGORA,
        ),
        False,
    )

    client = TestClient(app)
    resp = client.put(
        "/v1/admin/integracoes/ia.generativa--gemini",
        json={
            "servico": "ia.generativa",
            "provedor": "gemini",
            "conta_externa": "principal",
            "ambiente": "sandbox",
            "parametros": [{"nome": "model", "valor": "gemini-test"}],
            "credenciais": [{"papel": "api_key", "valor": ""}],
            "habilitada": True,
            "versao": 1,
        },
    )
    assert resp.status_code == 200


def test_put_nova_credencial_usa_write_canonico(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config_existente = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config_existente

    config_nova = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_2"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=2,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["app"].salvar_configuracao.return_value = (config_nova, True)

    client = TestClient(app)
    resp = client.put(
        "/v1/admin/integracoes/ia.generativa--gemini",
        json={
            "servico": "ia.generativa",
            "provedor": "gemini",
            "conta_externa": "principal",
            "ambiente": "sandbox",
            "parametros": [{"nome": "model", "valor": "gemini-test"}],
            "credenciais": [{"papel": "api_key", "valor": "nova-api-key"}],
            "habilitada": True,
            "versao": 1,
        },
    )
    assert resp.status_code == 200
    mocks["app"].salvar_configuracao.assert_called_once()


def test_put_habilitar_desabilitar_usa_put_sem_endpoint_paralelo(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config_existente = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=False,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config_existente

    config_nova = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=2,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["app"].salvar_configuracao.return_value = (config_nova, False)

    client = TestClient(app)
    resp = client.put(
        "/v1/admin/integracoes/ia.generativa--gemini",
        json={
            "servico": "ia.generativa",
            "provedor": "gemini",
            "conta_externa": "principal",
            "ambiente": "sandbox",
            "parametros": [{"nome": "model", "valor": "gemini-test"}],
            "credenciais": [],
            "habilitada": True,
            "versao": 1,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["habilitada"] is True


def test_healthcheck_suportado_funciona(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config

    client = TestClient(app)
    resp = client.post("/v1/admin/integracoes/ia.generativa--gemini/healthcheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["executado"] is True
    assert data["suportado"] is True
    assert data["provedor"] == "gemini"
    assert data["evidencia_ref"] is not None


def test_healthcheck_nao_suportado_retorna_contrato_sanitizado(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config = ConfiguracaoServicoExterno(
        configuracao_id="pagamentos.pix--pagbank",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="pagamentos.pix",
        provedor="pagbank",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("notification_url", "https://webhook"),),
        finalidades_credenciais=(("api_token", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=1,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config

    client = TestClient(app)
    resp = client.post("/v1/admin/integracoes/pagamentos.pix--pagbank/healthcheck")
    assert resp.status_code == 200
    data = resp.json()
    assert data["executado"] is False
    assert data["suportado"] is False
    assert data["provedor"] == "pagbank"
    assert data["erro"] == "healthcheck_nao_suportado_para_este_provedor"


def test_erro_dominio_resposta_sanitizada(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    mocks["service"].listar.side_effect = ErroConfiguracaoServico("configuracao_indisponivel")

    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 400
    assert "erro" in resp.json()


def test_concorrencia_versionamento_preservados(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)


    config_existente = ConfiguracaoServicoExterno(
        configuracao_id="ia.generativa--gemini",
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.SANDBOX,
        parametros_publicos=(("model", "gemini-test"),),
        finalidades_credenciais=(("api_key", "purpose_1"),),
        habilitada=True,
        homologada=False,
        evidencia_homologacao_ref=None,
        versao=2,
        atualizado_por=USUARIO,
        correlation_id="corr",
        atualizado_em=AGORA,
    )
    mocks["service"].obter.return_value = config_existente
    mocks["app"].salvar_configuracao.side_effect = ErroConfiguracaoServico("versao_configuracao_divergente")

    client = TestClient(app)
    resp = client.put(
        "/v1/admin/integracoes/ia.generativa--gemini",
        json={
            "servico": "ia.generativa",
            "provedor": "gemini",
            "conta_externa": "principal",
            "ambiente": "sandbox",
            "parametros": [{"nome": "model", "valor": "gemini-test"}],
            "credenciais": [],
            "habilitada": True,
            "versao": 1,
        },
    )
    assert resp.status_code == 409


def test_configuracao_outra_unidade_nao_acessivel(app_com_mocks):
    app, mocks = app_com_mocks
    ident = _identidade_admin()
    mocks["auth"].resolver_identidade.return_value = ident
    mocks["auth"].admin_status.return_value = (ident, True, None)
    mocks["service"].listar.return_value = ()

    client = TestClient(app)
    resp = client.get("/v1/admin/integracoes")
    assert resp.status_code == 200

    called_context = mocks["service"].listar.call_args[1]["contexto"]
    assert called_context.tenant_id == TENANT
    assert called_context.unidade_id == UNIDADE