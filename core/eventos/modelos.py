"""Objetos imutaveis compartilhados pela infraestrutura de eventos."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

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

_CHAVES_ENVELOPE_CANONICO = frozenset(
    {
        "event_id",
        "event_type",
        "aggregate_id",
        "aggregate_type",
        "tenant_id",
        "unit_id",
        "correlation_id",
        "causation_id",
        "idempotency_key",
        "timestamp",
        "version",
        "payload",
    }
)


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


def _texto_canonico(dados: Mapping[str, Any], chave: str) -> str:
    valor = dados[chave]
    if not isinstance(valor, str) or not valor.strip():
        raise MensagemInvalida()
    return valor.strip()


def _timestamp_canonico(valor: Any) -> datetime:
    if not isinstance(valor, str) or not valor.strip():
        raise MensagemInvalida()
    try:
        instante = datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise MensagemInvalida() from exc
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise MensagemInvalida()
    return instante


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
        if not isinstance(self.payload, Mapping):
            raise MensagemInvalida()
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise MensagemInvalida()
        object.__setattr__(
            self, "occurred_at", self.occurred_at.astimezone(timezone.utc)
        )
        object.__setattr__(self, "payload", _congelar(self.payload))

    @property
    def unit_id(self) -> UnidadeId:
        """Alias wire-canônico sem quebrar o nome interno legado."""
        return self.unidade_id

    @property
    def timestamp(self) -> datetime:
        """Alias wire-canônico sem quebrar o nome interno legado."""
        return self.occurred_at

    @classmethod
    def de_dict_canonico(cls, dados: Mapping[str, Any]) -> "EnvelopeMensagem":
        """Valida estritamente e reconstrói o contrato wire canônico."""
        if not isinstance(dados, Mapping) or set(dados) != _CHAVES_ENVELOPE_CANONICO:
            raise MensagemInvalida()
        payload = dados["payload"]
        version = dados["version"]
        causation_raw = dados["causation_id"]
        if not isinstance(payload, Mapping):
            raise MensagemInvalida()
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise MensagemInvalida()
        if causation_raw is not None and (
            not isinstance(causation_raw, str) or not causation_raw.strip()
        ):
            raise MensagemInvalida()
        return cls(
            event_id=EventoId.de(_texto_canonico(dados, "event_id")),
            event_type=_texto_canonico(dados, "event_type"),
            aggregate_id=_texto_canonico(dados, "aggregate_id"),
            aggregate_type=_texto_canonico(dados, "aggregate_type"),
            tenant_id=TenantId.de(_texto_canonico(dados, "tenant_id")),
            unidade_id=UnidadeId.de(_texto_canonico(dados, "unit_id")),
            correlation_id=CorrelationId.de(_texto_canonico(dados, "correlation_id")),
            causation_id=(
                CausationId.de(causation_raw.strip())
                if isinstance(causation_raw, str)
                else None
            ),
            idempotency_key=IdempotencyKey.de(
                _texto_canonico(dados, "idempotency_key")
            ),
            occurred_at=_timestamp_canonico(dados["timestamp"]),
            payload=payload,
            version=version,
        )

    def para_dict_canonico(self) -> dict[str, Any]:
        """Envelope wire estável da F14-C, com nomes independentes do legado interno."""
        return para_primitivo(
            {
                "event_id": str(self.event_id),
                "event_type": self.event_type,
                "aggregate_id": self.aggregate_id,
                "aggregate_type": self.aggregate_type,
                "tenant_id": str(self.tenant_id),
                "unit_id": str(self.unidade_id),
                "correlation_id": str(self.correlation_id),
                "causation_id": str(self.causation_id) if self.causation_id else None,
                "idempotency_key": str(self.idempotency_key),
                "timestamp": self.occurred_at,
                "version": self.version,
                "payload": _descongelar(self.payload),
            }
        )

    def para_dict(self) -> dict[str, Any]:
        """Serialização interna legada preservada para compatibilidade V1."""
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
