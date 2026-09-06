"""Contrato normalizado para transportes parceiros de marketplace.

99Food e Keeta publicam integração baseada em Open Delivery. Este protocolo
mantém o domínio independente das particularidades de autenticação, assinatura,
versão, URL e política de cancelamento de cada parceiro e só permite operação
quando o transporte injetado declara o contrato como verificado.
"""

from __future__ import annotations

from typing import Protocol

from .modelos import (
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    PedidoMarketplaceSnapshot,
    StatusPedidoExterno,
)


class TransporteParceiroNormalizado(Protocol):
    @property
    def contrato_verificado(self) -> bool: ...

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int
    ) -> tuple[EventoMarketplaceExterno, ...]: ...

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None: ...

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot: ...

    def executar_comando(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        comando: str,
        idempotency_key: str,
        status: StatusPedidoExterno | None = None,
        motivo: str | None = None,
    ) -> None: ...
