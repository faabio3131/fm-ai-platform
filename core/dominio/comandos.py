"""Mensagens de intenção; não contêm handlers nem acesso a infraestrutura."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .dinheiro import Dinheiro
from .enums import FormaPagamento, MotivoCancelamento, OrigemPedido, ProducaoStatus
from .ids import *
from .serializacao import Serializavel
from .tempo import em_utc
from .tipos import QuantidadeItem


@dataclass(frozen=True, kw_only=True)
class Comando(Serializavel):
    command_id: CommandId
    tenant_id: TenantId
    unidade_id: UnidadeId
    ator_id: UsuarioId
    correlation_id: CorrelationId
    causation_id: CausationId | None = None
    idempotency_key: IdempotencyKey | None = None
    solicitado_em: datetime
    versao: int = 1

    def __post_init__(self):
        object.__setattr__(self, "solicitado_em", em_utc(self.solicitado_em))


@dataclass(frozen=True, kw_only=True)
class CriarPedido(Comando):
    pedido_id: PedidoId
    origem: OrigemPedido


@dataclass(frozen=True, kw_only=True)
class AdicionarItemPedido(Comando):
    pedido_id: PedidoId
    item_id: PedidoItemId
    produto_id: ProdutoId
    quantidade: QuantidadeItem
    preco_unitario: Dinheiro


@dataclass(frozen=True, kw_only=True)
class RemoverItemPedido(Comando):
    pedido_id: PedidoId
    item_id: PedidoItemId


@dataclass(frozen=True, kw_only=True)
class ConfirmarPedido(Comando):
    pedido_id: PedidoId


@dataclass(frozen=True, kw_only=True)
class EnviarPedidoParaProducao(Comando):
    pedido_id: PedidoId


@dataclass(frozen=True, kw_only=True)
class CancelarPedido(Comando):
    pedido_id: PedidoId
    motivo: MotivoCancelamento


@dataclass(frozen=True, kw_only=True)
class RegistrarPagamento(Comando):
    pagamento_id: PagamentoId
    pedido_id: PedidoId
    valor: Dinheiro
    forma: FormaPagamento


@dataclass(frozen=True, kw_only=True)
class ConfirmarPagamento(Comando):
    pagamento_id: PagamentoId
    transacao_id: TransacaoPagamentoId


@dataclass(frozen=True, kw_only=True)
class SolicitarFechamentoComanda(Comando):
    comanda_id: ComandaId


@dataclass(frozen=True, kw_only=True)
class FecharComanda(Comando):
    comanda_id: ComandaId


@dataclass(frozen=True, kw_only=True)
class AtualizarStatusProducao(Comando):
    producao_item_id: ProducaoItemId
    status: ProducaoStatus


@dataclass(frozen=True, kw_only=True)
class AtribuirEntrega(Comando):
    entrega_id: EntregaId
    entregador_id: EntregadorId


@dataclass(frozen=True, kw_only=True)
class ConfirmarEntrega(Comando):
    entrega_id: EntregaId
    comprovante: dict[str, Any] = field(default_factory=dict)
