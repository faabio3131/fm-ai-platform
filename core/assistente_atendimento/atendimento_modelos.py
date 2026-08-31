"""Contratos imutáveis do domínio operacional do Assistente de Atendimento V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos import MetodoPagamento


class ModalidadePedidoAtendimento(StrEnum):
    INDEFINIDA = "indefinida"
    RETIRADA = "retirada"
    ENTREGA = "entrega"


class EstadoAtendimento(StrEnum):
    AGUARDANDO_DADOS_CLIENTE = "aguardando_dados_cliente"
    AGUARDANDO_MODALIDADE_ENTREGA = "aguardando_modalidade_entrega"
    AGUARDANDO_ENDERECO_ENTREGA = "aguardando_endereco_entrega"
    AGUARDANDO_FORMA_PAGAMENTO = "aguardando_forma_pagamento"
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
    modalidade: ModalidadePedidoAtendimento = ModalidadePedidoAtendimento.INDEFINIDA
    endereco_texto: str | None = None

    def __post_init__(self) -> None:
        if not self.cliente_nome.strip() or not self.resposta_cliente.strip():
            raise ValueError("intencao_atendimento_invalida")
        if self.endereco_texto is not None:
            endereco = " ".join(self.endereco_texto.split())
            object.__setattr__(self, "endereco_texto", endereco or None)
        if (
            self.modalidade is not ModalidadePedidoAtendimento.ENTREGA
            and self.endereco_texto is not None
        ):
            raise ValueError("endereco_sem_modalidade_entrega")


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
class CotacaoEntregaAtendimento:
    endereco_formatado: str
    cep: str
    place_id: str
    latitude: float
    longitude: float
    distancia_metros: int
    eta_rota_minutos: int
    area_id: str
    nome_area: str
    taxa: Decimal
    sla_minutos: int
    sla_maxutos: int
    versao_area: int

    def __post_init__(self) -> None:
        if any(
            not valor.strip()
            for valor in (
                self.endereco_formatado,
                self.cep,
                self.place_id,
                self.area_id,
                self.nome_area,
            )
        ):
            raise ValueError("cotacao_entrega_atendimento_invalida")
        cep = "".join(ch for ch in self.cep if ch.isdigit())
        if len(cep) != 8:
            raise ValueError("cep_entrega_atendimento_invalido")
        if self.distancia_metros < 0 or self.eta_rota_minutos < 1:
            raise ValueError("rota_entrega_atendimento_invalida")
        if self.sla_minutos < 1 or self.sla_maxutos < self.sla_minutos:
            raise ValueError("sla_entrega_atendimento_invalido")
        if self.versao_area < 1 or self.taxa < 0:
            raise ValueError("politica_entrega_atendimento_invalida")
        object.__setattr__(self, "cep", cep)


@dataclass(frozen=True)
class PreferenciaPagamentoAtendimento:
    metodo: MetodoPagamento
    valor_para_troco: Decimal | None = None

    def __post_init__(self) -> None:
        if self.valor_para_troco is None:
            return
        valor = Decimal(str(self.valor_para_troco)).quantize(Decimal("0.01"))
        if self.metodo is not MetodoPagamento.DINHEIRO:
            raise ValueError("troco_somente_para_dinheiro")
        if valor <= 0:
            raise ValueError("valor_para_troco_invalido")
        object.__setattr__(self, "valor_para_troco", valor)

    def troco_estimado(self, total: Decimal) -> Decimal:
        if self.valor_para_troco is None:
            return Decimal("0.00")
        total_q = Decimal(str(total)).quantize(Decimal("0.01"))
        if self.valor_para_troco < total_q:
            raise ValueError("valor_para_troco_inferior_total")
        return (self.valor_para_troco - total_q).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class CarrinhoAtendimento:
    tenant_id: str
    unidade_id: str
    conversa_id: str
    mensagem_id: str
    itens: tuple[ItemCarrinhoAtendimento, ...]
    fingerprint: str
    modalidade: ModalidadePedidoAtendimento = ModalidadePedidoAtendimento.INDEFINIDA
    endereco_solicitado: str | None = None
    entrega: CotacaoEntregaAtendimento | None = None
    pagamento: PreferenciaPagamentoAtendimento | None = None

    def __post_init__(self) -> None:
        if self.modalidade is ModalidadePedidoAtendimento.ENTREGA:
            return
        if self.entrega is not None:
            raise ValueError("cotacao_sem_modalidade_entrega")

    @property
    def subtotal(self) -> Decimal:
        return sum((item.subtotal for item in self.itens), start=Decimal(0))

    @property
    def taxa_entrega(self) -> Decimal:
        return self.entrega.taxa if self.entrega is not None else Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.subtotal + self.taxa_entrega


@dataclass(frozen=True)
class ResultadoCheckoutAssistente:
    pedido_id: str
    pedido_status: str
    pagamento_id: str | None = None
    pagamento_status: PagamentoStatus | None = None
    metodo_pagamento: MetodoPagamento | None = None
    estoque_reservado: bool = False
    estoque_idempotente: bool | None = None
    idempotente: bool = False


@dataclass(frozen=True)
class ResultadoAtendimento:
    estado: EstadoAtendimento
    mensagem: str
    carrinho: CarrinhoAtendimento | None = None
    checkout: ResultadoCheckoutAssistente | None = None
    handoff_motivo: str | None = None
    auditoria: tuple[tuple[str, str], ...] = field(default_factory=tuple)
