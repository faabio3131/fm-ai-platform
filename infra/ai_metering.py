"""Persistência durável e transacionalmente independente de AIUsageEvent."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from core.ai_router import AIUsageEvent


class AIMeteringBase(DeclarativeBase):
    pass


class AIUsageEventORM(AIMeteringBase):
    """Read model append-only de tentativas de execução de IA."""

    __tablename__ = "fm_ai_usage_events_v1"
    __table_args__ = (
        Index(
            "ix_fm_ai_usage_scope_time_v1",
            "tenant_id",
            "unidade_id",
            "timestamp",
        ),
        Index("ix_fm_ai_usage_corr_v1", "correlation_id"),
        Index("ix_fm_ai_usage_request_v1", "request_id"),
    )

    usage_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(96), nullable=False)
    provider: Mapped[str] = mapped_column(String(96), nullable=False)
    model: Mapped[str] = mapped_column(String(192), nullable=False)
    route_reason: Mapped[str] = mapped_column(Text, nullable=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(256))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    custo_real_calculado: Mapped[Decimal | None] = mapped_column(Numeric(38, 18))
    moeda: Mapped[str | None] = mapped_column(String(3))
    price_snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


def _event_id(evento: AIUsageEvent) -> str:
    material = (
        f"{evento.tenant_id}|{evento.unidade_id}|{evento.request_id}|"
        f"{evento.correlation_id}|{evento.provider}|{evento.model}|"
        f"{evento.outcome.value}|{evento.timestamp.isoformat()}"
    )
    return str(uuid5(NAMESPACE_URL, material))


class AIUsageDurableMetering:
    """Persiste cada tentativa em transação própria, fora da UoW de negócio."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def registrar(self, evento: AIUsageEvent) -> None:
        with self._session_factory() as session, session.begin():
            event_id = _event_id(evento)
            if session.get(AIUsageEventORM, event_id) is not None:
                return

            session.add(
                AIUsageEventORM(
                    usage_event_id=event_id,
                    tenant_id=evento.tenant_id,
                    unidade_id=evento.unidade_id,
                    request_id=evento.request_id,
                    correlation_id=evento.correlation_id,
                    capability=evento.capability.value,
                    provider=evento.provider,
                    model=evento.model,
                    route_reason=evento.route_reason,
                    fallback_used=evento.fallback_used,
                    fallback_reason=evento.fallback_reason,
                    input_tokens=evento.input_tokens,
                    output_tokens=evento.output_tokens,
                    cached_tokens=evento.cached_tokens,
                    latency_ms=evento.latency_ms,
                    outcome=evento.outcome.value,
                    custo_real_calculado=evento.custo_real_calculado,
                    moeda=evento.moeda,
                    price_snapshot_id=evento.price_snapshot_id,
                    timestamp=evento.timestamp,
                )
            )
