"""Roteamento comercial do Delivery Próprio usando o Google Maps canônico.

A camada Web não recebe chaves nem decide tenant/unidade. A identidade autenticada
resolve o contexto comercial; a fábrica de integrações só entrega o adapter quando
a configuração Google Maps do mesmo tenant/unidade está habilitada, homologada e
com credencial ativa no cofre.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from application.delivery_contexto_comercial import resolver_contexto_delivery_comercial
from core.integracoes.google_maps import Coordenada
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Permissao
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

GOOGLE_MAPS_CONFIG_ID = "mapas--google_maps"


@dataclass(frozen=True)
class RotaDeliveryGoogleMaps:
    cliente_id: str
    provedor: str
    origem_endereco: str
    destino_endereco: str
    distancia_metros: int
    distancia_km: float
    eta_minutos: int
    polyline_codificada: str
    origem_latitude: float
    origem_longitude: float
    destino_latitude: float
    destino_longitude: float
    origem_versao: int
    endereco_ref: str


def _exigir_permissoes(identidade: IdentidadeUsuario) -> None:
    obrigatorias = (
        Permissao.CLIENTE_VISUALIZAR,
        Permissao.PEDIDO_VISUALIZAR,
    )
    ausentes = [p.value for p in obrigatorias if p not in identidade.permissoes]
    if ausentes:
        raise PermissionError(
            "permissoes_delivery_maps_ausentes:" + ",".join(ausentes)
        )


def calcular_rota_delivery_google_maps_comercial(
    *,
    identidade: IdentidadeUsuario,
    cliente_id: str,
    session: Session,
) -> RotaDeliveryGoogleMaps:
    """Calcula distância/ETA reais sem expor segredo ou aceitar escopo livre."""

    _exigir_permissoes(identidade)
    contexto = resolver_contexto_delivery_comercial(
        session=session,
        identidade=identidade,
        cliente_id=cliente_id,
    )

    secret_store = EncryptedSQLAlchemySecretStore(session)
    maps = FabricaAdaptersExternos(
        session=session,
        secret_store=secret_store,
    ).google_maps(
        contexto=contexto.contexto,
        configuracao_id=GOOGLE_MAPS_CONFIG_ID,
    )

    origem = maps.geocodificar(contexto.origem_entrega.endereco_texto)
    destino = Coordenada(
        latitude=float(contexto.endereco.latitude),
        longitude=float(contexto.endereco.longitude),
    )
    rota = maps.calcular_rota(
        origem=origem.coordenada,
        destino=destino,
    )

    return RotaDeliveryGoogleMaps(
        cliente_id=contexto.cliente.cliente_id,
        provedor="google_maps",
        origem_endereco=origem.endereco_formatado,
        destino_endereco=contexto.endereco.endereco_formatado,
        distancia_metros=rota.distancia_metros,
        distancia_km=rota.distancia_km,
        eta_minutos=rota.eta_minutos,
        polyline_codificada=rota.polyline_codificada,
        origem_latitude=rota.origem.latitude,
        origem_longitude=rota.origem.longitude,
        destino_latitude=rota.destino.latitude,
        destino_longitude=rota.destino.longitude,
        origem_versao=contexto.origem_entrega.versao,
        endereco_ref=contexto.endereco.referencia,
    )
