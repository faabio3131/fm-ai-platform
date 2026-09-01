from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    ErroConfiguracaoServico,
    ServicoConfiguracoesExternas,
)
from core.integracoes.google_maps import RespostaHTTPMaps
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    FabricaAdaptersExternos,
    IntegrationConfigBase,
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.modelos_orm import SecurityBase


def _contexto(unidade: str) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id=unidade,
        usuario_id=f"admin-{unidade}",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({unidade}),
    )


def _servico(session: Session, store: ReferenceSecretStore) -> ServicoConfiguracoesExternas:
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )


def _configurar_maps(
    servico: ServicoConfiguracoesExternas,
    contexto: ContextoExecucao,
) -> None:
    servico.configurar(
        contexto=contexto,
        configuracao_id="maps-principal",
        servico="mapas",
        provedor="google_maps",
        conta_externa=f"billing-{contexto.unidade_id}",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "origin_address": f"Rua {contexto.unidade_id}",
            "country_code": "BR",
            "language": "pt-BR",
            "currency": "BRL",
        },
        finalidades_credenciais={
            "browser_api_key": "maps_browser_api_key",
            "server_api_key": "maps_server_api_key",
        },
        habilitada=True,
        versao_esperada=0,
    )


class _HTTPMapsCaptura:
    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def request(self, **kwargs):
        self.chamadas.append(kwargs)
        return RespostaHTTPMaps(
            status_code=200,
            payload={
                "status": "OK",
                "results": [
                    {
                        "formatted_address": "Rua Teste",
                        "place_id": "place-test",
                        "geometry": {"location": {"lat": -23.5, "lng": -46.6}},
                    }
                ],
            },
        )


def test_mesmo_tenant_nao_acessa_configuracao_de_outra_unidade() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore()

    with Session(engine) as session:
        servico = _servico(session, store)
        _configurar_maps(servico, _contexto("loja-1"))

        with pytest.raises(
            ErroConfiguracaoServico,
            match="configuracao_indisponivel",
        ):
            servico.obter(
                contexto=_contexto("loja-2"),
                configuracao_id="maps-principal",
            )

        _configurar_maps(servico, _contexto("loja-2"))
        assert servico.obter(
            contexto=_contexto("loja-1"),
            configuracao_id="maps-principal",
        ).conta_externa == "billing-loja-1"
        assert servico.obter(
            contexto=_contexto("loja-2"),
            configuracao_id="maps-principal",
        ).conta_externa == "billing-loja-2"


def test_fabrica_runtime_resolve_credencial_da_unidade_correta() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "l1-browser": "browser-loja-1",
            "l1-server": "server-loja-1",
            "l2-browser": "browser-loja-2",
            "l2-server": "server-loja-2",
        }
    )

    with Session(engine) as session:
        credenciais = ServicoCredenciaisReferenciadas(session, store)
        servico = _servico(session, store)

        for unidade, prefixo in (("loja-1", "l1"), ("loja-2", "l2")):
            contexto = _contexto(unidade)
            credenciais.rotacionar(
                contexto=contexto,
                provedor="google_maps",
                finalidade="maps_browser_api_key",
                nova_referencia=f"mapping:{prefixo}-browser",
            )
            credenciais.rotacionar(
                contexto=contexto,
                provedor="google_maps",
                finalidade="maps_server_api_key",
                nova_referencia=f"mapping:{prefixo}-server",
            )
            _configurar_maps(servico, contexto)
            servico.registrar_homologacao(
                contexto=contexto,
                configuracao_id="maps-principal",
                evidencia_ref=f"evidence://maps/{unidade}",
                versao_esperada=1,
            )

        fabrica = FabricaAdaptersExternos(session=session, secret_store=store)
        http_1 = _HTTPMapsCaptura()
        http_2 = _HTTPMapsCaptura()

        fabrica.google_maps(
            contexto=_contexto("loja-1"),
            configuracao_id="maps-principal",
            http=http_1,
        ).geocodificar("Rua A")
        fabrica.google_maps(
            contexto=_contexto("loja-2"),
            configuracao_id="maps-principal",
            http=http_2,
        ).geocodificar("Rua B")

        assert http_1.chamadas[0]["params"]["key"] == "server-loja-1"
        assert http_2.chamadas[0]["params"]["key"] == "server-loja-2"
        assert fabrica.chave_navegador_maps(
            contexto=_contexto("loja-1"),
            configuracao_id="maps-principal",
        ) == "browser-loja-1"
        assert fabrica.chave_navegador_maps(
            contexto=_contexto("loja-2"),
            configuracao_id="maps-principal",
        ) == "browser-loja-2"
