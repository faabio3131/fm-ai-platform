"""Persistência de entitlement comercial e projeção Kordena KCA-04."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EntitlementBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class FMCommercialEntitlementSnapshotORM(EntitlementBase):
    __tablename__ = "fm_commercial_entitlement_snapshots_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_account_id",
            "revision",
            name="uq_fm_commercial_entitlement_revision_v1",
        ),
        CheckConstraint(
            "revision >= 1", name="ck_fm_commercial_entitlement_revision_v1"
        ),
        CheckConstraint(
            "access_mode IN ('full','limited','billing_only','blocked')",
            name="ck_fm_commercial_entitlement_access_mode_v1",
        ),
        Index(
            "ix_fm_commercial_entitlement_account_v1",
            "product_account_id",
            "revision",
        ),
        Index(
            "ix_fm_commercial_entitlement_tenant_v1",
            "tenant_id",
            "revision",
        ),
    )

    entitlement_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    commercial_state: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_code: Mapped[str | None] = mapped_column(String(64))
    plan_version_id: Mapped[str | None] = mapped_column(String(64))
    access_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(128))


class KordenaEntitlementProjectionORM(EntitlementBase):
    __tablename__ = "fm_kordena_entitlement_projection_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_account_id",
            name="uq_kordena_entitlement_product_account_v1",
        ),
        CheckConstraint("revision >= 1", name="ck_kordena_entitlement_revision_v1"),
        CheckConstraint(
            "access_mode IN ('full','limited','billing_only','blocked')",
            name="ck_kordena_entitlement_access_mode_v1",
        ),
        Index(
            "ix_kordena_entitlement_state_v1",
            "commercial_state",
            "access_mode",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    commercial_state: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_code: Mapped[str | None] = mapped_column(String(64))
    plan_version_id: Mapped[str | None] = mapped_column(String(64))
    access_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    capabilities_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class KordenaEntitlementInboxORM(EntitlementBase):
    __tablename__ = "fm_kordena_entitlement_inbox_v1"
    __table_args__ = (
        Index(
            "ix_kordena_entitlement_inbox_account_v1",
            "product_account_id",
            "revision",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
