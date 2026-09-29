from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import AmbienteIntegracao, ServicoConfiguracoesExternas
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


def _contexto(tenant: str, unidade: str, usuario: str) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=tenant,
        unidade_id=unidade,
        usuario_id=usuario,
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{tenant}-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests.platform-managed",
        unidades_permitidas=frozenset({unidade}),
    )


class _MapsHTTP:
    def request(self, **kwargs):
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
                        "distanceMeters": 1200,
                        "duration": "300s",
                        "polyline": {"encodedPolyline": "abc"},
                    }
                ]
            },
        )


class _GeminiGateway:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return {"text": "ok"}


def _service(session: Session, store: ReferenceSecretStore):
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )


def _seed_legacy_fm_platform_configs(
    session: Session,
    store: ReferenceSecretStore,
) -> None:
    contexto = _contexto("tenant-legado-fm", "unidade-legado-fm", "fm-admin")
    credentials = ServicoCredenciaisReferenciadas(session, store)
    service = _service(session, store)

    credentials.rotacionar(
        contexto=contexto,
        provedor="google_maps",
        finalidade="mapas_browser_api_key",
        nova_referencia="mapping:maps-browser",
    )
    credentials.rotacionar(
        contexto=contexto,
        provedor="google_maps",
        finalidade="mapas_server_api_key",
        nova_referencia="mapping:maps-server",
    )
    service.configurar(
        contexto=contexto,
        configuracao_id="mapas--google_maps",
        servico="mapas",
        provedor="google_maps",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={"country_code": "BR", "language": "pt-BR"},
        finalidades_credenciais={
            "browser_api_key": "mapas_browser_api_key",
            "server_api_key": "mapas_server_api_key",
        },
        habilitada=True,
        versao_esperada=0,
    )
    service.registrar_homologacao(
        contexto=contexto,
        configuracao_id="mapas--google_maps",
        evidencia_ref="healthcheck://maps/legacy",
        versao_esperada=1,
    )

    credentials.rotacionar(
        contexto=contexto,
        provedor="gemini",
        finalidade="ia_generativa_api_key",
        nova_referencia="mapping:gemini",
    )
    service.configurar(
        contexto=contexto,
        configuracao_id="ia.generativa--gemini",
        servico="ia.generativa",
        provedor="gemini",
        conta_externa="principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={"model": "gemini-test"},
        finalidades_credenciais={"api_key": "ia_generativa_api_key"},
        habilitada=True,
        versao_esperada=0,
    )
    service.registrar_homologacao(
        contexto=contexto,
        configuracao_id="ia.generativa--gemini",
        evidencia_ref="healthcheck://gemini/legacy",
        versao_esperada=1,
    )


def test_novo_tenant_consumidor_usa_ponte_unica_fm_sem_copiar_segredos() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "maps-browser": "browser-fm",
            "maps-server": "server-fm",
            "gemini": "gemini-fm",
        }
    )
    consumidor = _contexto("tenant-novo", "unidade-nova", "user-novo")

    with Session(engine) as session:
        _seed_legacy_fm_platform_configs(session, store)
        factory = FabricaAdaptersExternos(session=session, secret_store=store)

        maps = factory.google_maps(
            contexto=consumidor,
            configuracao_id="mapas--google_maps",
            http=_MapsHTTP(),
        )
        geocode = maps.geocodificar("Av. Paulista")
        assert geocode.place_id == "place-1"
        assert (
            factory.chave_navegador_maps(
                contexto=consumidor,
                configuracao_id="mapas--google_maps",
            )
            == "browser-fm"
        )

        gateway = _GeminiGateway()
        gemini = factory.gemini(
            contexto=consumidor,
            configuracao_id="ia.generativa--gemini",
            gateway=gateway,
        )
        assert gemini.gerar("teste") == {"text": "ok"}
        assert gateway.calls[0]["api_key"] == "gemini-fm"
        assert gateway.calls[0]["model"] == "gemini-test"


def test_ponte_legada_falha_fechada_se_houver_mais_de_uma_autoridade() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "maps-browser": "browser-fm",
            "maps-server": "server-fm",
            "gemini": "gemini-fm",
            "maps-browser-2": "browser-fm-2",
            "maps-server-2": "server-fm-2",
        }
    )
    consumidor = _contexto("tenant-novo", "unidade-nova", "user-novo")

    with Session(engine) as session:
        _seed_legacy_fm_platform_configs(session, store)

        contexto_2 = _contexto("tenant-legado-2", "unidade-legado-2", "fm-admin-2")
        credentials = ServicoCredenciaisReferenciadas(session, store)
        service = _service(session, store)
        credentials.rotacionar(
            contexto=contexto_2,
            provedor="google_maps",
            finalidade="mapas_browser_api_key",
            nova_referencia="mapping:maps-browser-2",
        )
        credentials.rotacionar(
            contexto=contexto_2,
            provedor="google_maps",
            finalidade="mapas_server_api_key",
            nova_referencia="mapping:maps-server-2",
        )
        service.configurar(
            contexto=contexto_2,
            configuracao_id="mapas--google_maps",
            servico="mapas",
            provedor="google_maps",
            conta_externa="principal",
            ambiente=AmbienteIntegracao.HOMOLOGACAO,
            parametros_publicos={"country_code": "BR", "language": "pt-BR"},
            finalidades_credenciais={
                "browser_api_key": "mapas_browser_api_key",
                "server_api_key": "mapas_server_api_key",
            },
            habilitada=True,
            versao_esperada=0,
        )
        service.registrar_homologacao(
            contexto=contexto_2,
            configuracao_id="mapas--google_maps",
            evidencia_ref="healthcheck://maps/legacy-2",
            versao_esperada=1,
        )

        factory = FabricaAdaptersExternos(session=session, secret_store=store)
        try:
            factory.google_maps(
                contexto=consumidor,
                configuracao_id="mapas--google_maps",
                http=_MapsHTTP(),
            )
        except ValueError as exc:
            assert str(exc) == "configuracao_plataforma_legada_ambigua"
        else:
            raise AssertionError("fallback ambiguo deveria falhar fechado")
