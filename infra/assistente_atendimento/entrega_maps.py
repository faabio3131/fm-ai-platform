"""Cotação comercial de entrega do Assistente usando Delivery + Google Maps existentes."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.orm import Session

from core.assistente_atendimento.atendimento_modelos import CotacaoEntregaAtendimento
from core.assistente_atendimento.erros import ErroAssistenteAtendimento
from core.delivery.erros import ErroDelivery
from core.delivery.modelos import EnderecoDelivery, cep_normalizado
from core.delivery.servicos import _area_para_cep
from core.integracoes.google_maps import ErroGoogleMaps
from core.integracoes.modelos import ErroConfiguracaoServico
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretStore
from infra.delivery.politica_sqlalchemy import RepositorioPoliticaEntregaSQLAlchemy
from infra.integracoes.fabrica_adapters import FabricaAdaptersExternos
from infra.integracoes.repositorio_sqlalchemy import (
    RepositorioConfiguracoesExternasSQLAlchemy,
)


def _configuracao_maps_id(
    session: Session,
    *,
    contexto: ContextoExecucao,
) -> str:
    configs = RepositorioConfiguracoesExternasSQLAlchemy(session).listar(
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
    )
    candidatas = [
        config
        for config in configs
        if config.servico == "mapas"
        and config.provedor == "google_maps"
        and config.habilitada
        and config.homologada
    ]
    if not candidatas:
        raise ErroConfiguracaoServico("google_maps_nao_homologado_no_escopo")
    if len(candidatas) != 1:
        raise ErroConfiguracaoServico("google_maps_configuracao_ambigua")
    return candidatas[0].configuracao_id


class CotadorEntregaAssistenteGoogleMaps:
    """Valida endereço e aplica a política do domínio Delivery sem criar novo canal."""

    def __init__(
        self,
        session: Session,
        *,
        secret_store: SecretStore,
    ) -> None:
        self._session = session
        self._secret_store = secret_store
        self._politica = RepositorioPoliticaEntregaSQLAlchemy(session)

    def cotar(
        self,
        *,
        contexto: ContextoExecucao,
        cliente_ref: str,
        endereco_texto: str,
        cep_informado: str,
    ) -> CotacaoEntregaAtendimento:
        if not cliente_ref.strip() or not endereco_texto.strip():
            raise ErroAssistenteAtendimento("endereco_entrega_incompleto")

        origem = self._politica.obter_origem(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        areas = self._politica.listar_areas(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
        )
        if origem is None:
            raise ErroDelivery("origem_entrega_nao_configurada")
        if not areas:
            raise ErroDelivery("areas_entrega_nao_configuradas")

        config_id = _configuracao_maps_id(
            self._session,
            contexto=contexto,
        )
        maps = FabricaAdaptersExternos(
            session=self._session,
            secret_store=self._secret_store,
        ).google_maps(
            contexto=contexto,
            configuracao_id=config_id,
        )

        origem_geo = maps.geocodificar(origem.endereco_texto)
        destino_geo = maps.geocodificar(endereco_texto)
        cep = cep_normalizado(cep_informado)
        if destino_geo.cep is None or cep_normalizado(destino_geo.cep) != cep:
            raise ErroGoogleMaps("cep nao confirmado pela geocodificacao")

        componentes = (
            destino_geo.logradouro,
            destino_geo.numero,
            destino_geo.bairro,
            destino_geo.cidade,
            destino_geo.uf,
        )
        if any(not str(valor or "").strip() for valor in componentes):
            raise ErroGoogleMaps("endereco geocodificado incompleto para entrega")

        endereco = EnderecoDelivery(
            endereco_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"{contexto.tenant_id}:{contexto.unidade_id}:"
                    f"{cliente_ref}:{destino_geo.place_id}",
                )
            ),
            cliente_ref=cliente_ref,
            cep=cep,
            logradouro=str(destino_geo.logradouro),
            numero=str(destino_geo.numero),
            bairro=str(destino_geo.bairro),
            cidade=str(destino_geo.cidade),
            uf=str(destino_geo.uf),
            validado=True,
        )
        area = _area_para_cep(
            areas,
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            cep=endereco.cep,
        )
        rota = maps.calcular_rota(
            origem=origem_geo.coordenada,
            destino=destino_geo.coordenada,
        )

        return CotacaoEntregaAtendimento(
            endereco_formatado=destino_geo.endereco_formatado,
            cep=endereco.cep,
            place_id=destino_geo.place_id,
            latitude=destino_geo.coordenada.latitude,
            longitude=destino_geo.coordenada.longitude,
            distancia_metros=rota.distancia_metros,
            eta_rota_minutos=rota.eta_minutos,
            area_id=area.area_id,
            nome_area=area.nome,
            taxa=area.taxa,
            sla_minutos=area.sla_minutos,
            sla_maxutos=area.sla_maxutos,
            versao_area=area.versao,
        )
