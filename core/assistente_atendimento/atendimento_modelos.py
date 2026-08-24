"""Contratos imutáveis do domínio operacional do Assistente de Atendimento V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento


class EstadoAtendimento(StrEnum):
    AGUARDANDO_DADOS_CLIENTE = "aguardando_dados_cliente"
    AGUARDANDO_CONFIRMACAO_CLIENTE = "aguardando_confirmacao_cliente"
    CHECKOUT_REGISTRADO = "checkout_registrado"
    HANDOFF_HUMANO = "handoff_humano"


@dataclass(frozen=True)
class ProdutoCatalogoAtendimento:
    produto_id: str
    tenant_id: str
    unidade_id: str
    nome: str
    preco: Decimal
    ativo: bool = True

    def __post_init__(self) -> None:
        if (
            not self.produto_id.strip()
            or not self.tenant_id.strip()
            or not self.unidade_id.strip()
            or not self.nome.strip()
            or self.preco < 0
        ):
            raise ValueError("produto_catalogo_atendimento_invalido")


@dataclass(frozen=True)
class ItemIntencaoAtendimento:
    nome_produto: str
    quantidade: int

    def __post_init__(self) -> None:
        if (
            not self.nome_produto.strip()
            or self.quantidade < 1
            or self.quantidade > 100
        ):
            raise ValueError("item_intencao_atendimento_invalido")


@dataclass(frozen=True)
class IntencaoAtendimento:
    cliente_nome: str
    itens: tuple[ItemIntencaoAtendimento, ...]
    resposta_cliente: str

    def __post_init__(self) -> None:
        if not self.cliente_nome.strip() or not self.resposta_cliente.strip():
            raise ValueError("intencao_atendimento_invalida")


@dataclass(frozen=True)
class ItemCarrinhoAtendimento:
    produto_id: str
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade


@dataclass(frozen=True)
class CarrinhoAtendimento:
    tenant_id: str
    unidade_id: str
    conversa_id: str
    mensagem_id: str
    itens: tuple[ItemCarrinhoAtendimento, ...]
    fingerprint: str

    @property
    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.itens), start=Decimal(0))


@dataclass(frozen=True)
class ResultadoCheckoutAssistente:
    pedido_id: str
    pedido_status: str
    pagamento_id: str | None = None
    pagamento_status: PagamentoStatus | None = None
    metodo_pagamento: MetodoPagamento | None = None
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoAtendimento:
    estado: EstadoAtendimento
    mensagem: str
    carrinho: CarrinhoAtendimento | None = None
    checkout: ResultadoCheckoutAssistente | None = None
    handoff_motivo: str | None = None
    auditoria: tuple[tuple[str, str], ...] = field(default_factory=tuple)
