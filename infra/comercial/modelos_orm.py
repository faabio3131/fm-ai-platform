"""Modelos ORM do Commercial Registry KCA-01."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CommercialBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class FMCustomerORM(CommercialBase):
    __tablename__ = "fm_customers_v1"
    __table_args__ = (
        UniqueConstraint("customer_code", name="uq_fm_customer_code_v1"),
        CheckConstraint(
            "status IN ('active','suspended','closed')",
            name="ck_fm_customer_status_v1",
        ),
        CheckConstraint(
            "account_class IN ('internal_test','trial','paid','partner')",
            name="ck_fm_customer_account_class_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_customer_version_v1"),
        Index("ix_fm_customer_status_class_v1", "status", "account_class"),
        Index("ix_fm_customer_email_v1", "primary_contact_email"),
    )

    fm_customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    account_class: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    primary_contact_phone: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )


class FMProductAccountORM(CommercialBase):
    __tablename__ = "fm_product_accounts_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_code",
            "product_tenant_id",
            name="uq_fm_product_account_product_tenant_v1",
        ),
        CheckConstraint(
            "status IN ('requested','provisioning','active','suspended','closed')",
            name="ck_fm_product_account_status_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_product_account_version_v1"),
        Index(
            "ix_fm_product_account_customer_status_v1",
            "fm_customer_id",
            "status",
        ),
        Index("ix_fm_product_account_product_v1", "product_code"),
    )

    product_account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fm_customer_id: Mapped[str] = mapped_column(
        ForeignKey("fm_customers_v1.fm_customer_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    product_tenant_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommercialIdempotencyORM(CommercialBase):
    __tablename__ = "fm_commercial_idempotency_v1"

    scope: Mapped[str] = mapped_column(String(128), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(192), primary_key=True)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )


class CommercialAuditORM(CommercialBase):
    __tablename__ = "fm_commercial_audit_v1"
    __table_args__ = (
        Index("ix_fm_commercial_audit_aggregate_v1", "aggregate_type", "aggregate_id"),
        Index("ix_fm_commercial_audit_corr_v1", "correlation_id"),
        Index("ix_fm_commercial_audit_time_v1", "timestamp"),
    )

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(128))
    metadata_safe: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CommercialOutboxORM(CommercialBase):
    __tablename__ = "fm_commercial_outbox_v1"
    __table_args__ = (
        UniqueConstraint(
            "event_type",
            "idempotency_key",
            name="uq_fm_commercial_outbox_idempotency_v1",
        ),
        Index("ix_fm_commercial_outbox_status_v1", "status", "occurred_at"),
        Index("ix_fm_commercial_outbox_corr_v1", "correlation_id"),
        Index(
            "ix_fm_commercial_outbox_customer_v1",
            "fm_customer_id",
            "occurred_at",
        ),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fm_customer_id: Mapped[str | None] = mapped_column(String(64), index=True)
    product_account_id: Mapped[str | None] = mapped_column(String(64), index=True)
    product_code: Mapped[str | None] = mapped_column(String(64))
    product_tenant_id: Mapped[str | None] = mapped_column(String(64))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(192), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
