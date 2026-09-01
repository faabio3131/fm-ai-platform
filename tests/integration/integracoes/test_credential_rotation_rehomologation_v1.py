from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    EstadoProntidaoServico,
    ServicoConfiguracoesExternas,
)
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


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-rotation-rehomologation",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def _configurar(
    servico: ServicoConfiguracoesExternas,
    contexto: ContextoExecucao,
    *,
    versao_esperada: int,
    forcar_rehomologacao: bool = False,
):
    return servico.configurar(
        contexto=contexto,
        configuracao_id="maps-loja-1",
        servico="mapas",
        provedor="google_maps",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "origin_address": "Rua Exemplo, 100",
            "country_code": "BR",
            "language": "pt-BR",
            "currency": "BRL",
        },
        finalidades_credenciais={
            "browser_api_key": "maps_browser_api_key",
            "server_api_key": "maps_server_api_key",
        },
        habilitada=True,
        versao_esperada=versao_esperada,
        forcar_rehomologacao=forcar_rehomologacao,
    )


def test_rotacao_de_credencial_invalida_homologacao_ate_nova_evidencia() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "maps-browser-v1": "browser-key-v1",
            "maps-server-v1": "server-key-v1",
            "maps-server-v2": "server-key-v2",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        credenciais = ServicoCredenciaisReferenciadas(session, store)
        for finalidade, referencia in (
            ("maps_browser_api_key", "mapping:maps-browser-v1"),
            ("maps_server_api_key", "mapping:maps-server-v1"),
        ):
            credenciais.rotacionar(
                contexto=contexto,
                provedor="google_maps",
                finalidade=finalidade,
                nova_referencia=referencia,
            )

        auditoria = RepositorioAuditoriaEmMemoria()
        servico = ServicoConfiguracoesExternas(
            repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
            prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
            auditoria=auditoria,
        )

        configurada = _configurar(servico, contexto, versao_esperada=0)
        homologada = servico.registrar_homologacao(
            contexto=contexto,
            configuracao_id=configurada.configuracao_id,
            evidencia_ref="healthcheck://maps/v1-ok",
            versao_esperada=1,
        )
        assert homologada.homologada is True
        assert servico.avaliar(
            contexto=contexto, configuracao_id=homologada.configuracao_id
        ).estado is EstadoProntidaoServico.PRONTO

        credenciais.rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_server_api_key",
            nova_referencia="mapping:maps-server-v2",
        )
        apos_rotacao = _configurar(
            servico,
            contexto,
            versao_esperada=2,
            forcar_rehomologacao=True,
        )

        assert apos_rotacao.homologada is False
        assert apos_rotacao.evidencia_homologacao_ref is None
        assert servico.avaliar(
            contexto=contexto, configuracao_id=apos_rotacao.configuracao_id
        ).estado is EstadoProntidaoServico.CONFIGURADO
        assert "rehomologacao obrigatoria por rotacao de credencial" in auditoria.eventos[-1].motivo

