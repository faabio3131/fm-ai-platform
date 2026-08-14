from dataclasses import dataclass
from datetime import datetime

from .dinheiro import Dinheiro
from .enums import *
from .ids import *
from .serializacao import Serializavel
from .tempo import em_utc
from .tipos import QuantidadeItem


@dataclass(frozen=True, kw_only=True)
class Snapshot(Serializavel):
    tenant_id: TenantId
    unidade_id: UnidadeId
    atualizado_em: datetime
    versao: int = 1

    def __post_init__(self):
        object.__setattr__(self, "atualizado_em", em_utc(self.atualizado_em))


@dataclass(frozen=True, kw_only=True)
class PedidoItemSnapshot(Serializavel):
    item_id: PedidoItemId
    produto_id: ProdutoId
    quantidade: QuantidadeItem
    preco_unitario: Dinheiro


@dataclass(frozen=True, kw_only=True)
class PedidoSnapshot(Snapshot):
    pedido_id: PedidoId
    status: PedidoStatus
    origem: OrigemPedido
    total: Dinheiro
    itens: tuple[PedidoItemSnapshot, ...] = ()


@dataclass(frozen=True, kw_only=True)
class PagamentoSnapshot(Snapshot):
    pagamento_id: PagamentoId
    pedido_id: PedidoId
    status: PagamentoStatus
    valor: Dinheiro


@dataclass(frozen=True, kw_only=True)
class ComandaSnapshot(Snapshot):
    comanda_id: ComandaId
    status: ComandaStatus
    total: Dinheiro


@dataclass(frozen=True, kw_only=True)
class ProducaoSnapshot(Snapshot):
    producao_item_id: ProducaoItemId
    pedido_id: PedidoId
    status: ProducaoStatus


@dataclass(frozen=True, kw_only=True)
class EntregaSnapshot(Snapshot):
    entrega_id: EntregaId
    pedido_id: PedidoId
    status: EntregaStatus
    entregador_id: EntregadorId | None = None


@dataclass(frozen=True, kw_only=True)
class ClienteSnapshot(Snapshot):
    cliente_id: ClienteId
    nome: str


@dataclass(frozen=True, kw_only=True)
class ProdutoSnapshot(Snapshot):
    produto_id: ProdutoId
    nome: str
    preco: Dinheiro
