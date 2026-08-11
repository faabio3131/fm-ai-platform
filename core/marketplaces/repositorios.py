"""Repositórios mínimos do framework de marketplaces."""

from __future__ import annotations

from threading import RLock
from typing import Protocol

from .erros import ErroMarketplace
from .modelos import IntegracaoMarketplace, PedidoExterno


class RepositorioIntegracoesMarketplace(Protocol):
    def adicionar(self, integracao: IntegracaoMarketplace) -> None: ...

    def obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
    ) -> IntegracaoMarketplace | None: ...


class RepositorioIntegracoesMarketplaceEmMemoria:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str, str], IntegracaoMarketplace] = {}

    def adicionar(self, integracao: IntegracaoMarketplace) -> None:
        chave = (
            integracao.tenant_id,
            integracao.unidade_id,
            integracao.integracao_id,
        )
        with self._lock:
            if chave in self._dados:
                raise ErroMarketplace("integracao_duplicada")
            self._dados[chave] = integracao

    def obter(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        integracao_id: str,
    ) -> IntegracaoMarketplace | None:
        with self._lock:
            return self._dados.get((tenant_id, unidade_id, integracao_id))


class RepositorioPedidosExternos(Protocol):
    def obter(
        self, *, integracao_id: str, id_externo: str
    ) -> PedidoExterno | None: ...

    def salvar(self, pedido: PedidoExterno) -> PedidoExterno: ...

    def listar_integracao(self, integracao_id: str) -> tuple[PedidoExterno, ...]: ...


class RepositorioPedidosExternosEmMemoria:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dados: dict[tuple[str, str], PedidoExterno] = {}

    def obter(
        self, *, integracao_id: str, id_externo: str
    ) -> PedidoExterno | None:
        with self._lock:
            return self._dados.get((integracao_id, id_externo))

    def salvar(self, pedido: PedidoExterno) -> PedidoExterno:
        with self._lock:
            self._dados[(pedido.integracao_id, pedido.id_externo)] = pedido
            return pedido

    def listar_integracao(self, integracao_id: str) -> tuple[PedidoExterno, ...]:
        with self._lock:
            return tuple(
                pedido
                for (iid, _), pedido in self._dados.items()
                if iid == integracao_id
            )
