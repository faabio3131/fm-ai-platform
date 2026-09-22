"""Persistência da Saga de provisionamento KCA-05."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ProvisioningBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMCommercialProvisioningSagaORM(ProvisioningBase):
    __tablename__ = "fm_commercial_provisioning_sagas_v1"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_fm_provisioning_idempotency_v1"),
        UniqueConstraint("tenant_id", name="uq_fm_provisioning_tenant_v1"),
        Index("ix_fm_provisioning_status_v1", "status", "updated_at"),
        Index("ix_fm_provisioning_corr_v1", "correlation_id"),
    )

    provisioning_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    current_step: Mapped[str] = mapped_column(String(64), nullable=False)
    fm_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    product_account_id: Mapped[str | None] = mapped_column(String(64), index=True)
    identity_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    membership_id: Mapped[str | None] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    primary_contact_phone: Mapped[str | None] = mapped_column(String(64))
    trial_binding_status: Mapped[str] = mapped_column(String(32), nullable=False)
    entitlement_snapshot_id: Mapped[str | None] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class FMCommercialProvisioningInboxORM(ProvisioningBase):
    __tablename__ = "fm_commercial_provisioning_inbox_v1"
    __table_args__ = (
        Index("ix_fm_provisioning_inbox_time_v1", "received_at"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provisioning_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
