"""Agregado imutavel de Pedido V1, sem dependencias de persistencia."""

from dataclasses import dataclass, field
from datetime import datetime

from .dinheiro import Dinheiro
from .enums import CanalAtendimento, OrigemPedido, PedidoStatus
from .erros import PedidoInvalido
from .ids import (
    ClienteId,
    CorrelationId,
    IdempotencyKey,
    PedidoId,
    PedidoItemId,
    ProdutoId,
    TenantId,
    UnidadeId,
)
from .serializacao import Serializavel
from .tempo import em_utc
from .tipos import QuantidadeItem


@dataclass(frozen=True, kw_only=True)
class AdicionalItemPedido(Serializavel):
    id: str
    tenant_id: TenantId
    unidade_id: UnidadeId
    nome: str
    quantidade: QuantidadeItem
    preco_unitario: Dinheiro
    subtotal: Dinheiro

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.nome.strip():
            raise PedidoInvalido("Adicional exige id e nome")
        if self.subtotal != self.preco_unitario * self.quantidade.valor:
            raise PedidoInvalido("Subtotal do adicional inconsistente")


@dataclass(frozen=True, kw_only=True)
class ItemPedido(Serializavel):
    id: PedidoItemId
    tenant_id: TenantId
    unidade_id: UnidadeId
    produto_id: ProdutoId | None
    nome_produto: str
    quantidade: QuantidadeItem
    preco_unitario: Dinheiro
    subtotal: Dinheiro
    observacao: str | None = None
    ficha_versao: str | None = None
    adicionais: tuple[AdicionalItemPedido, ...] = ()

    def __post_init__(self) -> None:
        if not self.nome_produto.strip():
            raise PedidoInvalido("Snapshot do nome do produto e obrigatorio")
        adicionais = sum((a.subtotal.valor for a in self.adicionais), start=0)
        esperado = (self.preco_unitario.valor * self.quantidade.valor) + adicionais
        if self.subtotal.valor != esperado:
            raise PedidoInvalido("Subtotal do item inconsistente")


@dataclass(frozen=True, kw_only=True)
class ObservacaoPedido(Serializavel):
    id: str
    tenant_id: TenantId
    unidade_id: UnidadeId
    texto: str
    criado_em: datetime

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.texto.strip():
            raise PedidoInvalido("Observacao exige id e texto")
        object.__setattr__(self, "criado_em", em_utc(self.criado_em))


@dataclass(frozen=True, kw_only=True)
class Pedido(Serializavel):
    id: PedidoId
    tenant_id: TenantId
    unidade_id: UnidadeId
    origem: OrigemPedido
    canal: CanalAtendimento
    status: PedidoStatus
    cliente_id: ClienteId | None
    criado_em: datetime
    atualizado_em: datetime
    versao: int
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    subtotal: Dinheiro
    descontos: Dinheiro
    taxas: Dinheiro
    total: Dinheiro
    itens: tuple[ItemPedido, ...] = field(default_factory=tuple)
    observacoes: tuple[ObservacaoPedido, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "criado_em", em_utc(self.criado_em))
        object.__setattr__(self, "atualizado_em", em_utc(self.atualizado_em))
        if self.versao < 1:
            raise PedidoInvalido("Versao deve ser positiva")
        if self.status is not PedidoStatus.RASCUNHO:
            raise PedidoInvalido("Persistencia V1 aceita criacao em rascunho")
        filhos_fora_escopo = any(
            x.tenant_id != self.tenant_id or x.unidade_id != self.unidade_id
            for x in self.itens
        ) or any(
            x.tenant_id != self.tenant_id or x.unidade_id != self.unidade_id
            for x in self.observacoes
        )
        if filhos_fora_escopo:
            raise PedidoInvalido("Filho fora do escopo tenant/unidade")
        if (
            self.subtotal.valor - self.descontos.valor + self.taxas.valor
            != self.total.valor
        ):
            raise PedidoInvalido("Total do pedido inconsistente")
