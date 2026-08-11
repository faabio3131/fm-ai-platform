"""Adapter Keeta V1 sobre transporte parceiro validado.

O site oficial confirma integração por API para pedidos/cardápio/serviços, porém
os endpoints e payloads do parceiro não são públicos neste estágio. O adapter não
inventa contrato: exige transporte previamente validado com a documentação Keeta.
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
        del integracao, pedido_id_externo, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.CONFIRMAR)

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del integracao, pedido_id_externo, motivo, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.REJEITAR)

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> None:
        del integracao, pedido_id_externo, status, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.ATUALIZAR_STATUS)

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None:
        del integracao, pedido_id_externo, motivo, idempotency_key
        self.capacidades.exigir(CapacidadeMarketplace.CANCELAR)
