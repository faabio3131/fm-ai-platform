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
from core.integracoes.google_maps import Coordenada, RespostaHTTPMaps
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


def _contexto(unidade: str = "loja-1") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id=unidade,
        usuario_id=f"admin-{unidade}",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests.maps.runtime",
        unidades_permitidas=frozenset({unidade}),
    )


def _servico(session: Session, store: ReferenceSecretStore) -> ServicoConfiguracoesExternas:
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )


def _configurar_e_homologar_maps(
    *,
    session: Session,
    store: ReferenceSecretStore,
    contexto: ContextoExecucao,
    prefixo: str,
) -> None:
    credenciais = ServicoCredenciaisReferenciadas(session, store)
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
    servico = _servico(session, store)
    servico.configurar(
        contexto=contexto,
        configuracao_id="mapas--google_maps",
        servico="mapas",
        provedor="google_maps",
        conta_externa=f"maps-{contexto.unidade_id}",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "country_code": "BR",
            "language": "pt-BR",
        },
        finalidades_credenciais={
            "browser_api_key": "maps_browser_api_key",
            "server_api_key": "maps_server_api_key",
        },
        habilitada=True,
        versao_esperada=0,
    )
    servico.registrar_homologacao(
        contexto=contexto,
        configuracao_id="mapas--google_maps",
        evidencia_ref=f"evidence://maps/{contexto.unidade_id}",
        versao_esperada=1,
    )


class _HTTPMapsRuntime:
    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def request(self, **kwargs):
        self.chamadas.append(kwargs)
        if kwargs["method"] == "GET":
            return RespostaHTTPMaps(
                status_code=200,
                payload={
                    "status": "OK",
                    "results": [
                        {
                            "formatted_address": "Av. Paulista, Sao Paulo - SP",
                            "place_id": "place-1",
                            "geometry": {
                                "location": {"lat": -23.56, "lng": -46.65}
                            },
                        }
                    ],
                },
            )
        return RespostaHTTPMaps(
            status_code=200,
            payload={
                "routes": [
                    {
                        "distanceMeters": 7250,
                        "duration": "901s",
                        "polyline": {"encodedPolyline": "abc123"},
                    }
                ]
            },
        )


def test_google_maps_control_plane_resolve_chaves_e_executa_geocode_rota_eta() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "l1-browser": "browser-loja-1",
            "l1-server": "server-loja-1",
        }
    )
    contexto = _contexto("loja-1")

    with Session(engine) as session:
        _configurar_e_homologar_maps(
            session=session,
            store=store,
            contexto=contexto,
            prefixo="l1",
        )
        fabrica = FabricaAdaptersExternos(session=session, secret_store=store)
        http = _HTTPMapsRuntime()
        adapter = fabrica.google_maps(
            contexto=contexto,
            configuracao_id="mapas--google_maps",
            http=http,
        )

        geocode = adapter.geocodificar("Av. Paulista")
        rota = adapter.calcular_rota(
            origem=geocode.coordenada,
            destino=Coordenada(latitude=-23.50, longitude=-46.61),
        )

        assert geocode.place_id == "place-1"
        assert rota.distancia_km == 7.25
        assert rota.eta_minutos == 16
        assert http.chamadas[0]["params"]["key"] == "server-loja-1"
        assert http.chamadas[1]["headers"]["X-Goog-Api-Key"] == "server-loja-1"
        assert fabrica.chave_navegador_maps(
            contexto=contexto,
            configuracao_id="mapas--google_maps",
        ) == "browser-loja-1"


def test_google_maps_control_plane_falha_fechado_sem_homologacao() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "browser": "browser-key",
            "server": "server-key",
        }
    )
    contexto = _contexto("loja-1")

    with Session(engine) as session:
        credenciais = ServicoCredenciaisReferenciadas(session, store)
        credenciais.rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_browser_api_key",
            nova_referencia="mapping:browser",
        )
        credenciais.rotacionar(
            contexto=contexto,
            provedor="google_maps",
            finalidade="maps_server_api_key",
            nova_referencia="mapping:server",
        )
        _servico(session, store).configurar(
            contexto=contexto,
            configuracao_id="mapas--google_maps",
            servico="mapas",
            provedor="google_maps",
            conta_externa="maps-loja-1",
            ambiente=AmbienteIntegracao.HOMOLOGACAO,
            parametros_publicos={"country_code": "BR", "language": "pt-BR"},
            finalidades_credenciais={
                "browser_api_key": "maps_browser_api_key",
                "server_api_key": "maps_server_api_key",
            },
            habilitada=True,
            versao_esperada=0,
        )

        fabrica = FabricaAdaptersExternos(session=session, secret_store=store)
        with pytest.raises(ErroConfiguracaoServico, match="integracao_nao_homologada"):
            fabrica.google_maps(
                contexto=contexto,
                configuracao_id="mapas--google_maps",
                http=_HTTPMapsRuntime(),
            )
        with pytest.raises(ErroConfiguracaoServico, match="integracao_nao_homologada"):
            fabrica.chave_navegador_maps(
                contexto=contexto,
                configuracao_id="mapas--google_maps",
            )
