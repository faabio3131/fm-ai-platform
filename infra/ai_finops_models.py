"""Schema persistente do AI FinOps Read Model."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AIFinOpsBase(DeclarativeBase):
    pass


class AIFinOpsDailyORM(AIFinOpsBase):
    __tablename__ = "fm_ai_finops_daily_v1"
    __table_args__ = (
        Index(
            "ix_fm_ai_finops_scope_day_v1",
            "tenant_id",
            "unidade_id",
            "bucket_date",
        ),
        Index(
            "ix_fm_ai_finops_scope_provider_day_v1",
            "tenant_id",
            "unidade_id",
            "provider",
            "bucket_date",
        ),
    )

    aggregate_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(96), nullable=False)
    model: Mapped[str] = mapped_column(String(192), nullable=False)
    capability: Mapped[str] = mapped_column(String(96), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    fallback_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cached_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms_total: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms_max: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_known_events: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_unknown_events: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_total: Mapped[Decimal] = mapped_column(Numeric(38, 18), nullable=False)


class AIFinOpsProjectedEventORM(AIFinOpsBase):
    __tablename__ = "fm_ai_finops_projected_events_v1"

    usage_event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    projected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
