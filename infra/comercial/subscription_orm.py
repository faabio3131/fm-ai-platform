"""Persistência ORM do Subscription Engine KCA-08."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
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


class SubscriptionBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMCommercialSubscriptionORM(SubscriptionBase):
    __tablename__ = "fm_commercial_subscriptions_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_account_id",
            name="uq_fm_subscription_product_account_v1",
        ),
        CheckConstraint(
            "status IN ('pending','active','past_due','suspended','canceled')",
            name="ck_fm_subscription_status_v1",
        ),
        CheckConstraint(
            "contracted_amount >= 0",
            name="ck_fm_subscription_amount_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_subscription_version_v1"),
        Index(
            "ix_fm_subscription_customer_status_v1",
            "fm_customer_id",
            "status",
        ),
        Index(
            "ix_fm_subscription_tenant_status_v1",
            "tenant_id",
            "status",
        ),
        Index(
            "ix_fm_subscription_plan_v1",
            "plan_code",
            "plan_version_id",
        ),
    )

    subscription_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fm_customer_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    product_account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    price_id: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    contracted_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_now,
    )
