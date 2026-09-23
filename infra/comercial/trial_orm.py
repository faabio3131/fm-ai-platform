"""Persistência ORM do Trial Engine KCA-07."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class TrialBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMCommercialTrialPolicyORM(TrialBase):
    __tablename__ = "fm_commercial_trial_policies_v1"
    __table_args__ = (
        CheckConstraint("duration_days > 0", name="ck_fm_trial_policy_duration_v1"),
        Index("ix_fm_trial_policy_effective_v1", "active", "effective_from"),
    )

    policy_version: Mapped[str] = mapped_column(String(64), primary_key=True)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)


class FMCommercialTrialORM(TrialBase):
    __tablename__ = "fm_commercial_trials_v1"
    __table_args__ = (
        UniqueConstraint("product_account_id", name="uq_fm_trial_product_account_v1"),
        CheckConstraint(
            "status IN ('pending','active','converted','expired','revoked')",
            name="ck_fm_trial_status_v1",
        ),
        CheckConstraint("duration_days > 0", name="ck_fm_trial_duration_v1"),
        CheckConstraint("version >= 1", name="ck_fm_trial_version_v1"),
        Index("ix_fm_trial_customer_status_v1", "fm_customer_id", "status"),
        Index("ix_fm_trial_expiration_v1", "status", "ends_at"),
        Index("ix_fm_trial_tenant_v1", "tenant_id", "status"),
    )

    trial_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fm_customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    override_reason: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
