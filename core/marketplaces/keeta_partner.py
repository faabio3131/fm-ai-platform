"""Adapter Keeta V1 sobre transporte Open Delivery validado.

A Keeta publica OpenAPI baseada em Open Delivery, incluindo polling/webhook,
consulta, confirmação, pronto, despacho, entrega e cancelamento. OAuth e
assinatura permanecem fora do domínio, injetados pela camada de integração.
"""

from __future__ import annotations

from .erros import ErroMarketplace
from .modelos import (
    CapacidadeMarketplace,
    CapacidadesMarketplace,
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)
from .partner_transport import TransporteParceiroNormalizado

KEETA_CAPACIDADES_PUBLICAS = CapacidadesMarketplace(
    frozenset(
        {
            CapacidadeMarketplace.RECEBER_PEDIDO,
            CapacidadeMarketplace.CONFIRMAR,
            CapacidadeMarketplace.REJEITAR,
            CapacidadeMarketplace.ATUALIZAR_STATUS,
            CapacidadeMarketplace.CANCELAR,
            CapacidadeMarketplace.RECONCILIAR,
        }
    )
)


class KeetaPartnerAdapter:
    def __init__(self, transport: TransporteParceiroNormalizado) -> None:
        self.transport = transport

    @property
    def plataforma(self) -> PlataformaMarketplace:
        return PlataformaMarketplace.KEETA

    @property
    def capacidades(self) -> CapacidadesMarketplace:
        return KEETA_CAPACIDADES_PUBLICAS

    def _validar(self, integracao: IntegracaoMarketplace) -> None:
        if integracao.plataforma is not self.plataforma:
            raise ErroMarketplace("integracao_plataforma_incompativel")
        if not self.transport.contrato_verificado:
            raise ErroMarketplace("contrato_keeta_nao_verificado")

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int = 100
    ) -> tuple[EventoMarketplaceExterno, ...]:
        self._validar(integracao)
        return self.transport.receber_eventos(integracao, limite=limite)

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None:
        self._validar(integracao)
        self.transport.reconhecer_eventos(integracao, evento_ids)

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot:
        self._validar(integracao)
        return self.transport.consultar_pedido(integracao, pedido_id_externo)

    def confirmar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        idempotency_key: str,
    ) -> None:
        self._validar(integracao)
        self.transport.executar_comando(
            integracao,
            pedido_id_externo,
            comando="confirmar",
            idempotency_key=idempotency_key,
        )

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        self._validar(integracao)
        self.transport.executar_comando(
            integracao,
            pedido_id_externo,
            comando="rejeitar",
            motivo=motivo,
            idempotency_key=idempotency_key,
        )

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> None:
        self._validar(integracao)
        self.transport.executar_comando(
            integracao,
            pedido_id_externo,
            comando="atualizar_status",
            status=status,
            idempotency_key=idempotency_key,
        )

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        self._validar(integracao)
        self.transport.executar_comando(
            integracao,
            pedido_id_externo,
            comando="cancelar",
            motivo=motivo,
            idempotency_key=idempotency_key,
        )
