"""Contratos tipados na fronteira do PDV; valores V1 nunca usam float."""

from dataclasses import dataclass, field
from decimal import Decimal

from core.dominio.dinheiro import Dinheiro
from core.pagamentos.modelos import MetodoPagamento


def dinheiro_legado(valor: object) -> Dinheiro:
    """Converte o valor legado pela representacao decimal, inclusive float de UI."""
    if isinstance(valor, float):
        valor = str(valor)
    return Dinheiro(Decimal(str(valor)))


def dinheiro_zero() -> Dinheiro:
    return Dinheiro(Decimal(0))


def id_produto_legado(valor: object) -> str:
    return f"legacy:produto:{valor}"


def id_insumo_legado(valor: object) -> str:
    return f"legacy:insumo:{valor}"


def id_cliente_legado(valor: object | None) -> str | None:
    return None if valor is None else f"legacy:cliente:{valor}"


_METODOS = {
    "Dinheiro Em Espécie": MetodoPagamento.DINHEIRO,
    "Pix": MetodoPagamento.PIX,
    "Pix (Gerar QR Code Instantâneo)": MetodoPagamento.PIX,
    "Cartão Crédito": MetodoPagamento.CARTAO_CREDITO,
    "Cartão de Crédito": MetodoPagamento.CARTAO_CREDITO,
    "Cartão Débito": MetodoPagamento.CARTAO_DEBITO,
    "Cartão de Débito": MetodoPagamento.CARTAO_DEBITO,
}


def mapear_metodo(valor: str) -> MetodoPagamento:
    try:
        return _METODOS[valor]
    except KeyError as exc:
        raise ValueError("forma_pagamento_nao_suportada") from exc


@dataclass(frozen=True, kw_only=True)
class EntradaPDV:
    produto_id: int
    produto_nome: str
    quantidade: int
    preco_unitario: Dinheiro
    custo_total: Dinheiro
    forma_pagamento: str
    terminal_id: str
    checkout_id: str
    cliente_id: int | None = None
    valor_recebido: Dinheiro | None = None
    usar_cashback: bool = False
    desconto_cashback: Dinheiro = field(default_factory=dinheiro_zero)
    pix_sandbox: bool = False
    confirmacao_presencial: bool = False

    def __post_init__(self) -> None:
        if self.quantidade <= 0 or not self.checkout_id.strip():
            raise ValueError("entrada_pdv_invalida")
        if (
            not self.terminal_id.strip()
            or self.terminal_id != self.terminal_id.strip()
            or ":" in self.terminal_id
        ):
            raise ValueError("terminal_pdv_invalido")
        if self.desconto_cashback.valor < 0:
            raise ValueError("cashback_invalido")

    @property
    def subtotal(self) -> Dinheiro:
        return self.preco_unitario * self.quantidade

    @property
    def total(self) -> Dinheiro:
        return self.subtotal - self.desconto_cashback

    @property
    def idempotency_key(self) -> str:
        return f"pdv:{self.terminal_id}:{self.checkout_id}"


@dataclass(frozen=True)
class ResultadoPDV:
    modo: str
    sucesso: bool
    idempotente: bool = False
    pedido_id: str | None = None
    pagamento_id: str | None = None
    venda_financeira_id: str | None = None
    venda_legada_id: str | None = None
    troco: Dinheiro = field(default_factory=dinheiro_zero)
    motivo: str | None = None
