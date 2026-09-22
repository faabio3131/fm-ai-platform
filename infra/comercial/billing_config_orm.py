"""Persistência ORM de contas recebedoras e routing policies — KCA-09B."""

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


class BillingConfigBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMBillingProviderAccountORM(BillingConfigBase):
    __tablename__ = "fm_billing_provider_accounts_v1"
    __table_args__ = (
        CheckConstraint(
            "environment IN ('sandbox','production')",
            name="ck_fm_billing_provider_environment_v1",
        ),
        CheckConstraint(
            "status IN ('draft','validating','active','suspended','disabled')",
            name="ck_fm_billing_provider_status_v1",
        ),
        CheckConstraint(
            "last_test_status IN ('never','pass','fail')",
            name="ck_fm_billing_provider_test_status_v1",
        ),
        CheckConstraint("priority >= 0", name="ck_fm_billing_provider_priority_v1"),
        CheckConstraint("version >= 1", name="ck_fm_billing_provider_version_v1"),
        Index(
            "ix_fm_billing_provider_code_env_status_v1",
            "provider_code",
            "environment",
            "status",
        ),
    )

    provider_account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    legal_entity_ref: Mapped[str | None] = mapped_column(String(128))
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_secret_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    supported_payment_methods: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    supports_recurring: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    supports_webhooks: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="never"
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class FMBillingRoutingPolicyORM(BillingConfigBase):
    __tablename__ = "fm_billing_routing_policies_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_code",
            "payment_method",
            "environment",
            name="uq_fm_billing_routing_scope_v1",
        ),
        CheckConstraint(
            "environment IN ('sandbox','production')",
            name="ck_fm_billing_routing_environment_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_billing_routing_version_v1"),
        Index(
            "ix_fm_billing_routing_scope_active_v1",
            "product_code",
            "payment_method",
            "environment",
            "active",
        ),
    )

    routing_policy_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_provider_account_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    fallback_provider_account_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
