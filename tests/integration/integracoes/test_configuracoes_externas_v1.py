from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    ErroConfiguracaoServico,
    EstadoProntidaoServico,
    ServicoConfiguracoesExternas,
)
from core.integracoes.repositorios import ConflitoVersaoConfiguracao
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    IntegrationConfigBase,
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.modelos_orm import SecurityBase


def _contexto(*, tenant: str = "tenant-a", unidade: str = "loja-1") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{tenant}-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({unidade}),
    )


def _servico(session: Session, store: ReferenceSecretStore):
    auditoria = RepositorioAuditoriaEmMemoria()
    servico = ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=auditoria,
    )
    return servico, auditoria


def _configurar_maps(
    servico: ServicoConfiguracoesExternas,
    contexto: ContextoExecucao,
    *,
    versao_esperada: int = 0,
    origin_address: str = "Rua Exemplo, 100",
):
    return servico.configurar(
        contexto=contexto,
        configuracao_id="maps-loja-1",
        servico="mapas",
        provedor="google_maps",
        conta_externa="billing-account-tenant-a",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "origin_address": origin_address,
            "country_code": "BR",
            "language": "pt-BR",
            "currency": "BRL",
            "delivery_radius_km": 12,
        },
        finalidades_credenciais={
            "browser_api_key": "maps_browser_api_key",
            "server_api_key": "maps_server_api_key",
        },
        habilitada=True,
        versao_esperada=versao_esperada,
    )


def test_maps_so_fica_pronto_com_duas_chaves_e_homologacao_com_evidencia() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={"maps-browser": "browser-key", "maps-server": "server-key"}
    )
    contexto = _contexto()

    with Session(engine) as session:
        credenciais = ServicoCredenciaisReferenciadas(session, store)
        credenciais.rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_browser_api_key",
            nova_referencia="mapping:maps-browser",
        )
        credenciais.rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_server_api_key",
            nova_referencia="mapping:maps-server",
        )
        servico, auditoria = _servico(session, store)
        configuracao = _configurar_maps(servico, contexto)

        antes = servico.avaliar(
            contexto=contexto, configuracao_id=configuracao.configuracao_id
        )
        assert antes.estado is EstadoProntidaoServico.CONFIGURADO

        homologada = servico.registrar_homologacao(
            contexto=contexto,
            configuracao_id=configuracao.configuracao_id,
            evidencia_ref="evidence://maps/healthcheck-2026-08-14",
            versao_esperada=1,
        )
        depois = servico.avaliar(
            contexto=contexto, configuracao_id=homologada.configuracao_id
        )

        assert homologada.versao == 2
        assert depois.estado is EstadoProntidaoServico.PRONTO
        assert [evento.acao for evento in auditoria.eventos] == [
            "integracao.configurar",
            "integracao.homologar",
        ]
        assert all("key" not in str(evento.para_dict()) for evento in auditoria.eventos)

        alterada = _configurar_maps(
            servico,
            contexto,
            versao_esperada=2,
            origin_address="Avenida Nova, 200",
        )
        assert alterada.homologada is False
        assert alterada.evidencia_homologacao_ref is None
        assert (
            servico.avaliar(
                contexto=contexto, configuracao_id=alterada.configuracao_id
            ).estado
            is EstadoProntidaoServico.CONFIGURADO
        )


def test_maps_habilitado_sem_chave_de_servidor_fica_bloqueado() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(mapping={"maps-browser": "browser-key"})
    contexto = _contexto()

    with Session(engine) as session:
        ServicoCredenciaisReferenciadas(session, store).rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_browser_api_key",
            nova_referencia="mapping:maps-browser",
        )
        servico, _ = _servico(session, store)
        _configurar_maps(servico, contexto)
        status = servico.avaliar(
            contexto=contexto, configuracao_id="maps-loja-1"
        )

        assert status.estado is EstadoProntidaoServico.BLOQUEADO
        assert status.faltam_credenciais == ("maps_server_api_key",)


def test_configuracao_rejeita_segredo_em_parametro_publico() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    contexto = _contexto()

    with Session(engine) as session:
        servico, _ = _servico(session, ReferenceSecretStore())
        with pytest.raises(
            ErroConfiguracaoServico, match="segredo_em_parametro_publico"
        ):
            servico.configurar(
                contexto=contexto,
                configuracao_id="whatsapp-loja-1",
                servico="mensageria.whatsapp",
                provedor="meta",
                conta_externa="waba-1",
                ambiente=AmbienteIntegracao.HOMOLOGACAO,
                parametros_publicos={
                    "business_account_id": "waba-1",
                    "phone_number_id": "phone-1",
                    "app_id": "app-1",
                    "access_token": "nao-pode",
                },
                finalidades_credenciais={},
                habilitada=False,
                versao_esperada=0,
            )


def test_repositorio_isola_tenant_e_detecta_concorrencia_otimista() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    contexto = _contexto()

    with Session(engine) as session:
        servico, _ = _servico(session, ReferenceSecretStore())
        _configurar_maps(servico, contexto)

        with pytest.raises(
            ErroConfiguracaoServico, match="configuracao_indisponivel"
        ):
            servico.obter(
                contexto=_contexto(tenant="tenant-b"),
                configuracao_id="maps-loja-1",
            )

        # O mesmo nome local pode existir em outro tenant sem colisão nem vazamento.
        configuracao_tenant_b = _configurar_maps(
            servico, _contexto(tenant="tenant-b")
        )
        assert configuracao_tenant_b.tenant_id == "tenant-b"

        with pytest.raises(
            ConflitoVersaoConfiguracao, match="versao_configuracao_divergente"
        ):
            _configurar_maps(servico, contexto, versao_esperada=0)
