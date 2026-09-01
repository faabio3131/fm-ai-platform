"""Healthcheck externo real e escopado do Google Maps antes da homologação formal.

Valida Geocoding API e Routes API usando exclusivamente a chave de servidor já
armazenada no cofre. A chave de navegador é apenas confirmada como presente e
resolúvel; sua prova externa depende de uma jornada real no navegador.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.google_maps import ConfiguracaoGoogleMaps, GoogleMapsAdapter
from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.seguranca.modelos_orm import CredencialReferenciaORM

from .repositorio_sqlalchemy import RepositorioConfiguracoesExternasSQLAlchemy
from .transportes import RequestsGoogleMapsTransport

_ORIGEM = "Avenida Paulista, 1578, Sao Paulo - SP"
_DESTINO = "Praca da Se, Sao Paulo - SP"


@dataclass(frozen=True, kw_only=True)
class ResultadoHealthcheckGoogleMaps:
    evidencia_ref: str
    endereco_origem: str
    endereco_destino: str
    distancia_metros: int
    duracao_segundos: int
    browser_key_presente: bool


def _evidencia(
    *,
    contexto: ContextoExecucao,
    configuracao_id: str,
    origem: str,
    destino: str,
    distancia_metros: int,
    duracao_segundos: int,
    agora: datetime,
) -> str:
    instante = agora.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    material = "|".join(
        (
            contexto.tenant_id,
            contexto.unidade_id,
            configuracao_id,
            origem,
            destino,
            str(distancia_metros),
            str(duracao_segundos),
            instante,
        )
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"healthcheck://google-maps-server/{instante}/{digest}"


def _segredo_por_papel(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    provedor: str,
    finalidade: str,
) -> str:
    row = session.scalar(
        select(CredencialReferenciaORM)
        .where(
            CredencialReferenciaORM.tenant_id == contexto.tenant_id,
            CredencialReferenciaORM.unidade_id == contexto.unidade_id,
            CredencialReferenciaORM.provedor == provedor,
            CredencialReferenciaORM.finalidade == finalidade,
            CredencialReferenciaORM.ativa.is_(True),
        )
        .order_by(CredencialReferenciaORM.versao.desc())
        .limit(1)
    )
    if row is None:
        raise ErroConfiguracaoServico("credencial_indisponivel")
    return secret_store.resolve(row.referencia).reveal()


def executar_healthcheck_google_maps(
    *,
    session: Session,
    secret_store: SecretStore,
    contexto: ContextoExecucao,
    configuracao_id: str = "mapas--google_maps",
    agora: datetime | None = None,
    http=None,
) -> ResultadoHealthcheckGoogleMaps:
    """Executa geocodificação + rota reais sem exigir homologação prévia."""

    config = RepositorioConfiguracoesExternasSQLAlchemy(session).obter(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        configuracao_id=configuracao_id,
    )
    if config is None:
        raise ErroConfiguracaoServico("configuracao_indisponivel")
    if not config.habilitada:
        raise ErroConfiguracaoServico("integracao_desabilitada")
    if (config.servico, config.provedor) != ("mapas", "google_maps"):
        raise ErroConfiguracaoServico("adapter_incompativel")

    parametros = config.parametros
    language = str(parametros.get("language") or "").strip()
    country_code = str(parametros.get("country_code") or "").strip()
    server_finalidade = str(config.credenciais.get("server_api_key") or "").strip()
    browser_finalidade = str(config.credenciais.get("browser_api_key") or "").strip()
    if not language or not country_code or not server_finalidade or not browser_finalidade:
        raise ErroConfiguracaoServico("google_maps_configuracao_incompleta")

    server_api_key = _segredo_por_papel(
        session=session,
        secret_store=secret_store,
        contexto=contexto,
        provedor="google_maps",
        finalidade=server_finalidade,
    )
    browser_api_key = _segredo_por_papel(
        session=session,
        secret_store=secret_store,
        contexto=contexto,
        provedor="google_maps",
        finalidade=browser_finalidade,
    )
    if not browser_api_key.strip():
        raise ErroConfiguracaoServico("browser_api_key_indisponivel")

    adapter = GoogleMapsAdapter(
        configuracao=ConfiguracaoGoogleMaps(
            server_api_key=server_api_key,
            language=language,
            country_code=country_code,
            max_attempts=1,
        ),
        http=http or RequestsGoogleMapsTransport(),
    )
    try:
        origem = adapter.geocodificar(_ORIGEM)
        destino = adapter.geocodificar(_DESTINO)
        rota = adapter.calcular_rota(origem=origem.coordenada, destino=destino.coordenada)
    except Exception as exc:
        raise ErroConfiguracaoServico("google_maps_healthcheck_externo_falhou") from exc

    if rota.distancia_metros <= 0 or rota.duracao_segundos <= 0:
        raise ErroConfiguracaoServico("google_maps_healthcheck_resposta_invalida")

    return ResultadoHealthcheckGoogleMaps(
        evidencia_ref=_evidencia(
            contexto=contexto,
            configuracao_id=configuracao_id,
            origem=origem.endereco_formatado,
            destino=destino.endereco_formatado,
            distancia_metros=rota.distancia_metros,
            duracao_segundos=rota.duracao_segundos,
            agora=agora or datetime.now(timezone.utc),
        ),
        endereco_origem=origem.endereco_formatado,
        endereco_destino=destino.endereco_formatado,
        distancia_metros=rota.distancia_metros,
        duracao_segundos=rota.duracao_segundos,
        browser_key_presente=True,
    )
