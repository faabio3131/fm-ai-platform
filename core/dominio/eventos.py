from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from .ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from .serializacao import Serializavel
from .tempo import em_utc


@dataclass(frozen=True, kw_only=True)
class EventoDominio(Serializavel):
    TIPO: ClassVar[str] = "evento.dominio"
    event_id: EventoId
    aggregate_id: str
    aggregate_type: str
    tenant_id: TenantId
    unidade_id: UnidadeId
    correlation_id: CorrelationId
    causation_id: CausationId | None
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
    idempotency_key: IdempotencyKey | None = None
    version: int = 1

    @property
    def event_type(self):
        return self.TIPO

    def __post_init__(self):
        if not isinstance(self.correlation_id, CorrelationId):
            raise ValueError("correlation_id é obrigatório")
        object.__setattr__(self, "occurred_at", em_utc(self.occurred_at))

    def para_dict(self):
        result = super().para_dict()
        result["event_type"] = self.event_type
        return dict(sorted(result.items()))


@dataclass(frozen=True, kw_only=True)
class EventoPedidoOperacional(EventoDominio):
    """Evento tipado pela máquina normativa sem perder o nome operacional."""

    tipo_evento: str = "pedido.operacional.v1"

    @property
    def event_type(self):
        return self.tipo_evento

    def __post_init__(self):
        super().__post_init__()
        if not self.tipo_evento.strip() or not self.tipo_evento.startswith("pedido."):
            raise TypeError("tipo de evento operacional de pedido invalido")


@dataclass(frozen=True, kw_only=True)
class PedidoCriado(EventoDominio):
    TIPO: ClassVar[str] = "pedidocriado.v1"


@dataclass(frozen=True, kw_only=True)
class PedidoConfirmado(EventoDominio):
    TIPO: ClassVar[str] = "pedidoconfirmado.v1"


@dataclass(frozen=True, kw_only=True)
class PedidoEnviadoProducao(EventoDominio):
    TIPO: ClassVar[str] = "pedidoenviadoproducao.v1"


@dataclass(frozen=True, kw_only=True)
class PedidoCancelado(EventoDominio):
    TIPO: ClassVar[str] = "pedidocancelado.v1"


@dataclass(frozen=True, kw_only=True)
class ProducaoIniciada(EventoDominio):
    TIPO: ClassVar[str] = "producaoiniciada.v1"


@dataclass(frozen=True, kw_only=True)
class ProducaoPronta(EventoDominio):
    TIPO: ClassVar[str] = "producaopronta.v1"


@dataclass(frozen=True, kw_only=True)
class PagamentoConfirmado(EventoDominio):
    TIPO: ClassVar[str] = "pagamentoconfirmado.v1"


@dataclass(frozen=True, kw_only=True)
class ComandaFechada(EventoDominio):
    TIPO: ClassVar[str] = "comandafechada.v1"


@dataclass(frozen=True, kw_only=True)
class EntregaAtribuida(EventoDominio):
    TIPO: ClassVar[str] = "entregaatribuida.v1"


@dataclass(frozen=True, kw_only=True)
class EntregaConcluida(EventoDominio):
    TIPO: ClassVar[str] = "entregaconcluida.v1"


@dataclass(frozen=True, kw_only=True)
class EstoqueReservado(EventoDominio):
    TIPO: ClassVar[str] = "estoquereservado.v1"


@dataclass(frozen=True, kw_only=True)
class EstoqueBaixado(EventoDominio):
    TIPO: ClassVar[str] = "estoquebaixado.v1"


@dataclass(frozen=True, kw_only=True)
class EstoqueLiberado(EventoDominio):
    TIPO: ClassVar[str] = "estoqueliberado.v1"


@dataclass(frozen=True, kw_only=True)
class VendaCriada(EventoDominio):
    TIPO: ClassVar[str] = "vendacriada.v1"


@dataclass(frozen=True, kw_only=True)
class ClienteConsentiuMarketing(EventoDominio):
    TIPO: ClassVar[str] = "clienteconsentiu_marketing.v1"


@dataclass(frozen=True, kw_only=True)
class ClienteCancelouMarketing(EventoDominio):
    TIPO: ClassVar[str] = "clientecancelou_marketing.v1"