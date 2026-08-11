"""Portas do framework de marketplaces e registro de adapters."""

from __future__ import annotations

from typing import Protocol

from .erros import ErroMarketplace
from .modelos import (
    CapacidadesMarketplace,
    EventoMarketplaceExterno,
    IntegracaoMarketplace,
    PedidoExterno,
    PedidoMarketplaceSnapshot,
    PlataformaMarketplace,
    StatusPedidoExterno,
)


class MarketplaceAdapter(Protocol):
    @property
    def plataforma(self) -> PlataformaMarketplace: ...

    @property
    def capacidades(self) -> CapacidadesMarketplace: ...

    def receber_eventos(
        self, integracao: IntegracaoMarketplace, *, limite: int = 100
    ) -> tuple[EventoMarketplaceExterno, ...]: ...

    def reconhecer_eventos(
        self, integracao: IntegracaoMarketplace, evento_ids: tuple[str, ...]
    ) -> None: ...

    def consultar_pedido(
        self, integracao: IntegracaoMarketplace, pedido_id_externo: str
    ) -> PedidoMarketplaceSnapshot: ...

    def confirmar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        idempotency_key: str,
    ) -> None: ...

    def rejeitar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None: ...

    def atualizar_status(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> None: ...

    def cancelar(
        self,
        integracao: IntegracaoMarketplace,
        pedido_id_externo: str,
        *,
        motivo: str,
        idempotency_key: str,
    ) -> None: ...


class PortaPedidosMarketplaceInternos(Protocol):
    def criar_ou_obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> tuple[str, bool]: ...

    def atualizar_status_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        status: StatusPedidoExterno,
        idempotency_key: str,
    ) -> str: ...

    def reconciliar_marketplace(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido: PedidoExterno,
        snapshot: PedidoMarketplaceSnapshot,
        idempotency_key: str,
    ) -> str: ...


class RegistroAdaptersMarketplace:
    def __init__(self) -> None:
        self._adapters: dict[PlataformaMarketplace, MarketplaceAdapter] = {}

    def registrar(self, adapter: MarketplaceAdapter) -> None:
        if adapter.plataforma in self._adapters:
            raise ErroMarketplace("adapter_duplicado")
        self._adapters[adapter.plataforma] = adapter

    def obter(self, plataforma: PlataformaMarketplace) -> MarketplaceAdapter:
        try:
            return self._adapters[plataforma]
        except KeyError as exc:
            raise ErroMarketplace("adapter_nao_registrado") from exc
