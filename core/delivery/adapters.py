"""Portas do Delivery Próprio V1.

O canal não toca ORM legado nem declara pagamentos como aprovados. As integrações
com Pedido, Pagamento, Entrega e promoções entram por estas portas.
"""

from __future__ import annotations

from typing import Protocol

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento

from .modelos import (
    CarrinhoDelivery,
    CupomDelivery,
    EventoTracking,
    PagamentoDeliveryRef,
    PedidoDelivery,
)


class PortaCarrinhosDelivery(Protocol):
    def criar(self, carrinho: CarrinhoDelivery) -> CarrinhoDelivery: ...

    def obter(
        self, *, tenant_id: str, unidade_id: str, carrinho_id: str
    ) -> CarrinhoDelivery | None: ...

    def salvar_cas(
        self, carrinho: CarrinhoDelivery, *, expected_version: int
    ) -> CarrinhoDelivery: ...


class PortaPedidosDelivery(Protocol):
    def registrar(
        self, *, pedido: PedidoDelivery, idempotency_key: str
    ) -> tuple[PedidoDelivery, bool]: ...

    def obter(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> PedidoDelivery | None: ...

    def cancelar(
        self,
        *,
        pedido: PedidoDelivery,
        idempotency_key: str,
    ) -> tuple[PedidoDelivery, bool]: ...


class PortaPagamentosDelivery(Protocol):
    def criar_obrigacao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> PagamentoDeliveryRef: ...

    def consultar(
        self, *, tenant_id: str, unidade_id: str, pedido_id: str
    ) -> PagamentoDeliveryRef: ...

    def cancelar_ou_estornar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        idempotency_key: str,
    ) -> PagamentoStatus: ...


class PortaEntregaCanalDelivery(Protocol):
    def criar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        endereco_id: str,
        idempotency_key: str,
    ) -> str: ...

    def timeline(
        self, *, tenant_id: str, unidade_id: str, entrega_id: str
    ) -> tuple[EventoTracking, ...]: ...

    def cancelar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        entrega_id: str,
        motivo: str,
        idempotency_key: str,
    ) -> bool: ...


class PortaPromocoesDelivery(Protocol):
    def reservar_cupom(
        self,
        *,
        cupom: CupomDelivery,
        cliente_ref: str,
        carrinho_id: str,
        desconto: str,
        idempotency_key: str,
    ) -> str: ...

    def reservar_cashback(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        cliente_ref: str,
        carrinho_id: str,
        valor_maximo: str,
        idempotency_key: str,
    ) -> str: ...

    def validar_reservas(self, carrinho: CarrinhoDelivery) -> None: ...

    def confirmar_reservas(self, *, carrinho: CarrinhoDelivery, pedido_id: str) -> None: ...

    def estornar_reservas(
        self, *, carrinho: CarrinhoDelivery, pedido_id: str
    ) -> tuple[str, bool]: ...
