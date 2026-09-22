"""Persistência ORM de Webhook Inbox, Billing Ledger e Reconciliation — KCA-10."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class BillingEventsBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMBillingSubscriptionBindingORM(BillingEventsBase):
    __tablename__ = "fm_billing_subscription_bindings_v1"
    __table_args__ = (
        UniqueConstraint(
            "provider_account_id",
            "external_subscription_ref",
            name="uq_fm_billing_subscription_external_v1",
        ),
        UniqueConstraint(
            "provider_account_id",
            "subscription_id",
            name="uq_fm_billing_subscription_internal_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_billing_binding_version_v1"),
        Index(
            "ix_fm_billing_binding_provider_subscription_v1",
            "provider_code",
            "subscription_id",
        ),
    )

    billing_binding_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    subscription_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_subscription_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    external_customer_ref: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class FMBillingWebhookInboxORM(BillingEventsBase):
    __tablename__ = "fm_billing_webhook_inbox_v1"
    __table_args__ = (
        UniqueConstraint(
            "provider_account_id",
            "external_event_id",
            name="uq_fm_billing_webhook_event_v1",
        ),
        CheckConstraint(
            "status IN ('received','verified','processing','processed',"
            "'failed_retryable','dead_letter','ignored_out_of_order','rejected')",
            name="ck_fm_billing_webhook_status_v1",
        ),
        CheckConstraint("attempts >= 0", name="ck_fm_billing_webhook_attempts_v1"),
        CheckConstraint(
            "max_attempts >= 1", name="ck_fm_billing_webhook_max_attempts_v1"
        ),
        CheckConstraint("version >= 1", name="ck_fm_billing_webhook_version_v1"),
        Index(
            "ix_fm_billing_webhook_status_received_v1",
            "status",
            "received_at",
        ),
        Index(
            "ix_fm_billing_webhook_subscription_order_v1",
            "subscription_id",
            "provider_occurred_at",
        ),
        Index(
            "ix_fm_billing_webhook_transaction_v1",
            "external_transaction_ref",
        ),
    )

    inbox_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_event_type: Mapped[str | None] = mapped_column(String(128))
    canonical_event_type: Mapped[str | None] = mapped_column(String(64))
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    provider_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_sequence: Mapped[int | None] = mapped_column(Integer)
    external_subscription_ref: Mapped[str | None] = mapped_column(String(255))
    external_transaction_ref: Mapped[str | None] = mapped_column(String(255))
    subscription_id: Mapped[str | None] = mapped_column(String(64), index=True)
    normalized_payload: Mapped[dict | None] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class FMBillingTransactionORM(BillingEventsBase):
    __tablename__ = "fm_billing_transactions_v1"
    __table_args__ = (
        UniqueConstraint(
            "provider_account_id",
            "external_transaction_ref",
            name="uq_fm_billing_transaction_external_v1",
        ),
        CheckConstraint(
            "transaction_type IN ('payment','refund')",
            name="ck_fm_billing_transaction_type_v1",
        ),
        CheckConstraint(
            "status IN ('pending','succeeded','failed','refunded')",
            name="ck_fm_billing_transaction_status_v1",
        ),
        CheckConstraint(
            "reconciliation_status IN ('not_checked','in_sync','repaired','failed')",
            name="ck_fm_billing_transaction_reconciliation_v1",
        ),
        CheckConstraint(
            "amount IS NULL OR amount >= 0",
            name="ck_fm_billing_transaction_amount_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_billing_transaction_version_v1"),
        Index(
            "ix_fm_billing_transaction_subscription_v1",
            "subscription_id",
            "updated_at",
        ),
        Index(
            "ix_fm_billing_transaction_reconcile_v1",
            "reconciliation_status",
            "last_reconciled_at",
        ),
    )

    billing_transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_transaction_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(64), index=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    provider_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_sequence: Mapped[int | None] = mapped_column(Integer)
    last_external_event_id: Mapped[str | None] = mapped_column(String(255))
    reconciliation_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_checked"
    )
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )


class FMBillingReconciliationRunORM(BillingEventsBase):
    __tablename__ = "fm_billing_reconciliation_runs_v1"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started','in_sync','repaired','failed')",
            name="ck_fm_billing_reconciliation_status_v1",
        ),
        Index(
            "ix_fm_billing_reconciliation_transaction_v1",
            "billing_transaction_id",
            "started_at",
        ),
    )

    reconciliation_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    billing_transaction_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    provider_status: Mapped[str | None] = mapped_column(String(32))
    final_status: Mapped[str | None] = mapped_column(String(32))
    error_code: Mapped[str | None] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
