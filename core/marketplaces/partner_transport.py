"""Contrato normalizado para provedores sem especificação pública completa.

PR18 não inventa endpoints, autenticação ou payloads de 99Food/Keeta. O adapter
só pode operar quando um transporte parceiro, validado contra a documentação
fornecida pela plataforma, é injetado explicitamente.
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
