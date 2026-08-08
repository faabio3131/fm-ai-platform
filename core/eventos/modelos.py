"""Objetos imutaveis compartilhados pela infraestrutura de eventos."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.dominio.serializacao import Serializavel, para_primitivo
from core.seguranca.auditoria import sanitizar_metadata

from .erros import MensagemInvalida


def _congelar(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return MappingProxyType({str(k): _congelar(v) for k, v in valor.items()})
    if isinstance(valor, (list, tuple)):
        return tuple(_congelar(v) for v in valor)
    if isinstance(valor, set):
        return frozenset(_congelar(v) for v in valor)
    return valor


def _descongelar(valor: Any) -> Any:
    if isinstance(valor, Mapping):
        return {str(k): _descongelar(v) for k, v in valor.items()}
    if isinstance(valor, (tuple, frozenset)):
        return [_descongelar(v) for v in valor]
    return valor


@dataclass(frozen=True)
class EnvelopeMensagem(Serializavel):
    event_id: EventoId
    event_type: str
    aggregate_id: str
    aggregate_type: str
    tenant_id: TenantId
    unidade_id: UnidadeId
    correlation_id: CorrelationId
    causation_id: CausationId | None
    idempotency_key: IdempotencyKey
    occurred_at: datetime
    payload: Mapping[str, Any]
    version: int = 1

    def __post_init__(self) -> None:
        if not all(
            isinstance(v, str) and v.strip()
            for v in (self.event_type, self.aggregate_id, self.aggregate_type)
        ):
            raise MensagemInvalida()
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise MensagemInvalida()
        if not isinstance(self.version, int) or self.version < 1:
            raise MensagemInvalida()
        object.__setattr__(
            self, "occurred_at", self.occurred_at.astimezone(timezone.utc)
        )
        object.__setattr__(self, "payload", _congelar(self.payload))

    def para_dict(self) -> dict[str, Any]:
        return para_primitivo(
            {
                "event_id": str(self.event_id),
                "event_type": self.event_type,
                "aggregate_id": self.aggregate_id,
                "aggregate_type": self.aggregate_type,
                "tenant_id": str(self.tenant_id),
                "unidade_id": str(self.unidade_id),
                "correlation_id": str(self.correlation_id),
                "causation_id": str(self.causation_id) if self.causation_id else None,
                "idempotency_key": str(self.idempotency_key),
                "occurred_at": self.occurred_at,
                "payload": _descongelar(self.payload),
                "version": self.version,
            }
        )


class ClassificacaoErro(str, Enum):
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


@dataclass(frozen=True)
class ErroNormalizado(Serializavel):
    tipo: str
    mensagem: str
    classificacao: ClassificacaoErro


@dataclass(frozen=True)
class DeadLetter(Serializavel):
    mensagem: EnvelopeMensagem
    motivo: str
    ultimo_erro: ErroNormalizado
    tentativas: int
    timestamp: datetime
    tenant_id: TenantId
    unidade_id: UnidadeId
    correlation_id: CorrelationId
    metadata: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    @classmethod
    def criar(
        cls,
        mensagem: EnvelopeMensagem,
        motivo: str,
        erro: ErroNormalizado,
        tentativas: int,
        timestamp: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> "DeadLetter":
        return cls(
            mensagem,
            motivo,
            erro,
            tentativas,
            timestamp.astimezone(timezone.utc),
            mensagem.tenant_id,
            mensagem.unidade_id,
            mensagem.correlation_id,
            sanitizar_metadata(metadata),
        )


class StatusProcessamento(str, Enum):
    PROCESSADO = "processed"
    DUPLICADO = "duplicate"
    RETRY = "retry"
    DLQ = "dlq"


@dataclass(frozen=True)
class ResultadoProcessamento(Serializavel):
    status: StatusProcessamento
    event_id: EventoId
    attempts: int
    next_attempt_at: datetime | None = None
    erro: ErroNormalizado | None = None
