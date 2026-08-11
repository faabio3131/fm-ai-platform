"""Portas de Pedido/Pagamento/Handoff da Mica V1 e fakes determinísticos."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento

from .modelos import (
    PagamentoRegistradoMica,
    PedidoRegistradoMica,
    PedidoSolicitadoMica,
)


class PortaPedidosMica(Protocol):
    def registrar_confirmado(self, pedido: PedidoSolicitadoMica) -> PedidoRegistradoMica: ...


class PortaPagamentosMica(Protocol):
    def criar_obrigacao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> PagamentoRegistradoMica: ...


class PortaHandoffMica(Protocol):
    def registrar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        conversa_id: str,
        motivo: str,
    ) -> None: ...


@dataclass
class OperacaoMicaFake(PortaPedidosMica, PortaPagamentosMica, PortaHandoffMica):
    """Fake test-only. Não cria Venda, não baixa estoque e não confirma pagamento."""

    status_pagamento: PagamentoStatus = PagamentoStatus.PENDENTE

    def __post_init__(self) -> None:
        self.pedidos: dict[tuple[str, str, str], PedidoRegistradoMica] = {}
        self.pagamentos: dict[tuple[str, str, str], PagamentoRegistradoMica] = {}
        self.handoffs: list[tuple[str, str, str, str]] = []
        self.chamadas_pedido = 0
        self.chamadas_pagamento = 0

    def registrar_confirmado(self, pedido: PedidoSolicitadoMica) -> PedidoRegistradoMica:
        chave = (pedido.tenant_id, pedido.unidade_id, pedido.idempotency_key)
        existente = self.pedidos.get(chave)
        if existente:
            return PedidoRegistradoMica(existente.pedido_id, existente.status, True)
        self.chamadas_pedido += 1
        registrado = PedidoRegistradoMica(str(uuid4()), "confirmado")
        self.pedidos[chave] = registrado
        return registrado

    def criar_obrigacao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        valor: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> PagamentoRegistradoMica:
        chave = (tenant_id, unidade_id, idempotency_key)
        existente = self.pagamentos.get(chave)
        if existente:
            return PagamentoRegistradoMica(
                existente.pagamento_id, existente.status, existente.metodo, True
            )
        self.chamadas_pagamento += 1
        status = (
            PagamentoStatus.AGUARDANDO_ENTREGA
            if metodo is MetodoPagamento.PAGAMENTO_NA_ENTREGA
            else self.status_pagamento
        )
        registrado = PagamentoRegistradoMica(str(uuid4()), status, metodo)
        self.pagamentos[chave] = registrado
        return registrado

    def registrar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        conversa_id: str,
        motivo: str,
    ) -> None:
        evento = (tenant_id, unidade_id, conversa_id, motivo)
        if evento not in self.handoffs:
            self.handoffs.append(evento)
