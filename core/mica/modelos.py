"""Contratos imutáveis da Mica V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento


class EstadoAtendimentoMica(StrEnum):
    AGUARDANDO_CONFIRMACAO = "aguardando_confirmacao"
    PEDIDO_CONFIRMADO = "pedido_confirmado"
    HANDOFF_HUMANO = "handoff_humano"


@dataclass(frozen=True)
class ProdutoCatalogoMica:
    produto_id: str
    tenant_id: str
    unidade_id: str
    nome: str
    preco: Decimal
    ativo: bool = True

    def __post_init__(self) -> None:
        if not self.produto_id.strip() or not self.nome.strip() or self.preco < 0:
            raise ValueError("produto_catalogo_invalido")


@dataclass(frozen=True)
class ItemIntencaoMica:
    nome_produto: str
    quantidade: int

    def __post_init__(self) -> None:
        if not self.nome_produto.strip() or self.quantidade < 1 or self.quantidade > 100:
            raise ValueError("item_intencao_invalido")


@dataclass(frozen=True)
class IntencaoMica:
    cliente_nome: str
    itens: tuple[ItemIntencaoMica, ...]
    resposta_whatsapp: str

    def __post_init__(self) -> None:
        if not self.cliente_nome.strip() or not self.resposta_whatsapp.strip():
            raise ValueError("intencao_mica_invalida")


@dataclass(frozen=True)
class ItemCarrinhoMica:
    produto_id: str
    nome_produto: str
    quantidade: int
    preco_unitario: Decimal

    @property
    def subtotal(self) -> Decimal:
        return self.preco_unitario * self.quantidade


@dataclass(frozen=True)
class CarrinhoMica:
    tenant_id: str
    unidade_id: str
    conversa_id: str
    mensagem_id: str
    itens: tuple[ItemCarrinhoMica, ...]
    fingerprint: str

    @property
    def total(self) -> Decimal:
        return sum((item.subtotal for item in self.itens), start=Decimal("0"))


@dataclass(frozen=True)
class PedidoSolicitadoMica:
    tenant_id: str
    unidade_id: str
    carrinho: CarrinhoMica
    cliente_ref: str
    idempotency_key: str


@dataclass(frozen=True)
class PedidoRegistradoMica:
    pedido_id: str
    status: str
    idempotente: bool = False


@dataclass(frozen=True)
class PagamentoRegistradoMica:
    pagamento_id: str
    status: PagamentoStatus
    metodo: MetodoPagamento
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoAtendimentoMica:
    estado: EstadoAtendimentoMica
    mensagem: str
    carrinho: CarrinhoMica | None = None
    pedido: PedidoRegistradoMica | None = None
    pagamento: PagamentoRegistradoMica | None = None
    handoff_motivo: str | None = None
    auditoria: tuple[tuple[str, str], ...] = field(default_factory=tuple)
