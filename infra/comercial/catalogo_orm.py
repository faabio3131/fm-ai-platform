"""Persistência ORM do catálogo comercial KCA-03."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CatalogBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class FMCommercialPlanORM(CatalogBase):
    __tablename__ = "fm_commercial_plans_v1"
    __table_args__ = (
        UniqueConstraint(
            "product_code",
            "plan_code",
            name="uq_fm_commercial_plan_code_v1",
        ),
        UniqueConstraint(
            "product_code",
            "rank",
            name="uq_fm_commercial_plan_rank_v1",
        ),
        CheckConstraint(
            "status IN ('configuration_pending','configured','revoked')",
            name="ck_fm_commercial_plan_status_v1",
        ),
        CheckConstraint("rank BETWEEN 1 AND 4", name="ck_fm_commercial_plan_rank_v1"),
        CheckConstraint("version >= 1", name="ck_fm_commercial_plan_version_v1"),
        Index("ix_fm_commercial_plan_product_v1", "product_code", "rank"),
    )

    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
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


class FMCommercialPlanVersionORM(CatalogBase):
    __tablename__ = "fm_commercial_plan_versions_v1"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "version_number",
            name="uq_fm_commercial_plan_version_number_v1",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published','revoked')",
            name="ck_fm_commercial_plan_version_status_v1",
        ),
        CheckConstraint(
            "version_number >= 1",
            name="ck_fm_commercial_plan_version_number_v1",
        ),
        Index(
            "ix_fm_commercial_plan_version_plan_status_v1",
            "plan_id",
            "status",
            "version_number",
        ),
        Index(
            "ix_fm_commercial_plan_version_validity_v1",
            "plan_id",
            "valid_from",
            "valid_until",
        ),
    )

    plan_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("fm_commercial_plans_v1.plan_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    trial_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    marketing_badge: Mapped[str | None] = mapped_column(String(96))
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_by: Mapped[str | None] = mapped_column(String(64))
    published_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FMCommercialPlanEntitlementORM(CatalogBase):
    __tablename__ = "fm_commercial_plan_entitlements_v1"
    __table_args__ = (
        UniqueConstraint(
            "plan_version_id",
            "capability_key",
            name="uq_fm_commercial_plan_entitlement_v1",
        ),
        Index(
            "ix_fm_commercial_plan_entitlement_version_v1",
            "plan_version_id",
            "capability_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "fm_commercial_plan_versions_v1.plan_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    capability_key: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    limit_unit: Mapped[str | None] = mapped_column(String(32))
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class FMCommercialPriceORM(CatalogBase):
    __tablename__ = "fm_commercial_prices_v1"
    __table_args__ = (
        UniqueConstraint(
            "plan_version_id",
            "currency",
            "billing_period",
            "revision",
            name="uq_fm_commercial_price_revision_v1",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published','revoked')",
            name="ck_fm_commercial_price_status_v1",
        ),
        CheckConstraint("revision >= 1", name="ck_fm_commercial_price_revision_v1"),
        CheckConstraint("amount >= 0", name="ck_fm_commercial_price_amount_v1"),
        Index(
            "ix_fm_commercial_price_lookup_v1",
            "plan_version_id",
            "currency",
            "billing_period",
            "status",
        ),
    )

    price_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "fm_commercial_plan_versions_v1.plan_version_id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    billing_period: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    change_policy: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_by: Mapped[str | None] = mapped_column(String(64))
    published_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FMCommercialPromotionORM(CatalogBase):
    __tablename__ = "fm_commercial_promotions_v1"
    __table_args__ = (
        UniqueConstraint(
            "promotion_code",
            name="uq_fm_commercial_promotion_code_v1",
        ),
        CheckConstraint(
            "status IN ('configuration_pending','configured','revoked')",
            name="ck_fm_commercial_promotion_status_v1",
        ),
        CheckConstraint("version >= 1", name="ck_fm_commercial_promotion_version_v1"),
        Index(
            "ix_fm_commercial_promotion_product_v1",
            "product_code",
            "status",
        ),
    )

    promotion_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    promotion_code: Mapped[str] = mapped_column(String(32), nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
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


class FMCommercialPromotionVersionORM(CatalogBase):
    __tablename__ = "fm_commercial_promotion_versions_v1"
    __table_args__ = (
        UniqueConstraint(
            "promotion_id",
            "version_number",
            name="uq_fm_commercial_promotion_version_number_v1",
        ),
        CheckConstraint(
            "status IN ('draft','validated','published','revoked')",
            name="ck_fm_commercial_promotion_version_status_v1",
        ),
        CheckConstraint(
            "discount_type IN ('percentage','fixed_amount','fixed_price')",
            name="ck_fm_commercial_promotion_discount_type_v1",
        ),
        CheckConstraint(
            "discount_value > 0",
            name="ck_fm_commercial_promotion_discount_value_v1",
        ),
        Index(
            "ix_fm_commercial_promotion_version_promotion_v1",
            "promotion_id",
            "status",
            "version_number",
        ),
        Index(
            "ix_fm_commercial_promotion_version_window_v1",
            "starts_at",
            "ends_at",
        ),
    )

    promotion_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    promotion_id: Mapped[str] = mapped_column(
        ForeignKey("fm_commercial_promotions_v1.promotion_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    discount_type: Mapped[str] = mapped_column(String(32), nullable=False)
    discount_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_redemptions: Mapped[int | None] = mapped_column(Integer)
    per_customer_limit: Mapped[int | None] = mapped_column(Integer)
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    change_reason: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_by: Mapped[str | None] = mapped_column(String(64))
    published_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FMCommercialPromotionPlanORM(CatalogBase):
    __tablename__ = "fm_commercial_promotion_plans_v1"
    __table_args__ = (
        UniqueConstraint(
            "promotion_version_id",
            "plan_id",
            name="uq_fm_commercial_promotion_plan_v1",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_version_id: Mapped[str] = mapped_column(
        ForeignKey(
            "fm_commercial_promotion_versions_v1.promotion_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("fm_commercial_plans_v1.plan_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
