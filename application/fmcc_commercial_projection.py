"""Read-only commercial projection exposed to FM Control Center — KCA-12.

FMCC never reads Kordena tables directly. This boundary materializes only the
commercial data contract that FMCC is allowed to consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select

from infra.comercial.billing_events_orm import FMBillingTransactionORM
from infra.comercial.catalogo_sqlalchemy import RepositorioCatalogoComercialSQLAlchemy
from infra.comercial.entitlement_orm import KordenaEntitlementProjectionORM
from infra.comercial.modelos_orm import FMCustomerORM, FMProductAccountORM
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.comercial.trial_orm import FMCommercialTrialORM
from infra.seguranca.modelos_orm import (
    IdentityMembershipORM,
    IdentityMembershipUnitORM,
)

SCHEMA_VERSION = "kordena.fmcc.commercial.v1"


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    normalized = _utc(value)
    return normalized.isoformat() if normalized is not None else None


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _after(value: datetime | None, reference: datetime) -> bool:
    normalized = _utc(value)
    return normalized is not None and normalized > reference


def _at_or_before(value: datetime | None, reference: datetime) -> bool:
    normalized = _utc(value)
    return normalized is not None and normalized <= reference


def _fact(
    *,
    external_id: str,
    fact_type: str,
    payload: dict[str, Any],
    source_timestamp: datetime,
) -> dict[str, Any]:
    return {
        "external_id": external_id,
        "fact_type": fact_type,
        "payload": payload,
        "source_timestamp": _iso(source_timestamp),
    }


class AplicacaoFMCCCommercialProjectionV1:
    """Creates the canonical FMCC read contract without moving authority."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def snapshot(self, *, agora: datetime | None = None) -> dict[str, Any]:
        instante = _utc(agora or datetime.now(timezone.utc))
        assert instante is not None

        with self._session_factory() as session:
            accounts = tuple(
                session.scalars(
                    select(FMProductAccountORM)
                    .where(FMProductAccountORM.product_code == "KORDENA")
                    .order_by(
                        FMProductAccountORM.created_at,
                        FMProductAccountORM.product_account_id,
                    )
                ).all()
            )
            account_ids = tuple(row.product_account_id for row in accounts)
            customer_ids = tuple(
                dict.fromkeys(row.fm_customer_id for row in accounts)
            )
            tenant_ids = tuple(
                dict.fromkeys(
                    row.product_tenant_id
                    for row in accounts
                    if row.product_tenant_id is not None
                )
            )

            customers = (
                tuple(
                    session.scalars(
                        select(FMCustomerORM)
                        .where(FMCustomerORM.fm_customer_id.in_(customer_ids))
                        .order_by(
                            FMCustomerORM.created_at,
                            FMCustomerORM.fm_customer_id,
                        )
                    ).all()
                )
                if customer_ids
                else ()
            )
            trials = (
                tuple(
                    session.scalars(
                        select(FMCommercialTrialORM)
                        .where(
                            FMCommercialTrialORM.product_account_id.in_(account_ids)
                        )
                        .order_by(
                            FMCommercialTrialORM.created_at,
                            FMCommercialTrialORM.trial_id,
                        )
                    ).all()
                )
                if account_ids
                else ()
            )
            subscriptions = (
                tuple(
                    session.scalars(
                        select(FMCommercialSubscriptionORM)
                        .where(
                            FMCommercialSubscriptionORM.product_account_id.in_(
                                account_ids
                            )
                        )
                        .order_by(
                            FMCommercialSubscriptionORM.created_at,
                            FMCommercialSubscriptionORM.subscription_id,
                        )
                    ).all()
                )
                if account_ids
                else ()
            )
            subscription_ids = tuple(
                row.subscription_id for row in subscriptions
            )
            transactions = (
                tuple(
                    session.scalars(
                        select(FMBillingTransactionORM)
                        .where(
                            FMBillingTransactionORM.subscription_id.in_(
                                subscription_ids
                            )
                        )
                        .order_by(
                            FMBillingTransactionORM.updated_at,
                            FMBillingTransactionORM.billing_transaction_id,
                        )
                    ).all()
                )
                if subscription_ids
                else ()
            )
            entitlements = (
                tuple(
                    session.scalars(
                        select(KordenaEntitlementProjectionORM)
                        .where(
                            KordenaEntitlementProjectionORM.tenant_id.in_(
                                tenant_ids
                            )
                        )
                        .order_by(KordenaEntitlementProjectionORM.tenant_id)
                    ).all()
                )
                if tenant_ids
                else ()
            )

            membership_counts = dict(
                session.execute(
                    select(
                        IdentityMembershipORM.tenant_id,
                        func.count(IdentityMembershipORM.membership_id),
                    )
                    .where(IdentityMembershipORM.product_code == "KORDENA")
                    .group_by(IdentityMembershipORM.tenant_id)
                ).all()
            )
            unit_counts = dict(
                session.execute(
                    select(
                        IdentityMembershipORM.tenant_id,
                        func.count(
                            func.distinct(IdentityMembershipUnitORM.unidade_id)
                        ),
                    )
                    .join(
                        IdentityMembershipUnitORM,
                        IdentityMembershipUnitORM.membership_id
                        == IdentityMembershipORM.membership_id,
                    )
                    .where(IdentityMembershipORM.product_code == "KORDENA")
                    .group_by(IdentityMembershipORM.tenant_id)
                ).all()
            )

            catalog_repo = RepositorioCatalogoComercialSQLAlchemy(session)
            catalog = self._catalog_snapshot(catalog_repo, instante)

        facts = self._facts(
            customers=customers,
            trials=trials,
            subscriptions=subscriptions,
            transactions=transactions,
            entitlements=entitlements,
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "product_code": "KORDENA",
            "as_of": _iso(instante),
            "customers": [
                {
                    "fm_customer_id": row.fm_customer_id,
                    "customer_code": row.customer_code,
                    "display_name": row.display_name,
                    "status": row.status,
                    "account_class": row.account_class,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                }
                for row in customers
            ],
            "product_accounts": [
                {
                    "product_account_id": row.product_account_id,
                    "fm_customer_id": row.fm_customer_id,
                    "product_code": row.product_code,
                    "product_tenant_id": row.product_tenant_id,
                    "status": row.status,
                    "version": row.version,
                    "created_at": _iso(row.created_at),
                    "updated_at": _iso(row.updated_at),
                }
                for row in accounts
            ],
            "trials": [
                {
                    "trial_id": row.trial_id,
                    "fm_customer_id": row.fm_customer_id,
                    "product_account_id": row.product_account_id,
                    "tenant_id": row.tenant_id,
                    "plan_code": row.plan_code,
                    "plan_version_id": row.plan_version_id,
                    "status": row.status,
                    "started_at": _iso(row.started_at),
                    "ends_at": _iso(row.ends_at),
                    "converted_at": _iso(row.converted_at),
                    "revoked_at": _iso(row.revoked_at),
                    "version": row.version,
                }
                for row in trials
            ],
            "subscriptions": [
                {
                    "subscription_id": row.subscription_id,
                    "fm_customer_id": row.fm_customer_id,
                    "product_account_id": row.product_account_id,
                    "tenant_id": row.tenant_id,
                    "plan_code": row.plan_code,
                    "plan_version_id": row.plan_version_id,
                    "price_id": row.price_id,
                    "currency": row.currency,
                    "billing_period": row.billing_period,
                    "contracted_amount": str(row.contracted_amount),
                    "status": row.status,
                    "current_period_start": _iso(row.current_period_start),
                    "current_period_end": _iso(row.current_period_end),
                    "cancel_at_period_end": row.cancel_at_period_end,
                    "canceled_at": _iso(row.canceled_at),
                    "activated_at": _iso(row.activated_at),
                    "suspended_at": _iso(row.suspended_at),
                    "version": row.version,
                    "updated_at": _iso(row.updated_at),
                }
                for row in subscriptions
            ],
            "billing_transactions": [
                {
                    "billing_transaction_id": row.billing_transaction_id,
                    "provider_code": row.provider_code,
                    "subscription_id": row.subscription_id,
                    "transaction_type": row.transaction_type,
                    "status": row.status,
                    "amount": _decimal(row.amount),
                    "currency": row.currency,
                    "reconciliation_status": row.reconciliation_status,
                    "provider_occurred_at": _iso(row.provider_occurred_at),
                    "updated_at": _iso(row.updated_at),
                }
                for row in transactions
            ],
            "entitlements": [
                {
                    "tenant_id": row.tenant_id,
                    "product_account_id": row.product_account_id,
                    "revision": row.revision,
                    "commercial_state": row.commercial_state,
                    "plan_code": row.plan_code,
                    "plan_version_id": row.plan_version_id,
                    "access_mode": row.access_mode,
                    "effective_from": _iso(row.effective_from),
                    "valid_until": _iso(row.valid_until),
                    "last_synced_at": _iso(row.last_synced_at),
                }
                for row in entitlements
            ],
            "catalog": catalog,
            "organization": [
                {
                    "tenant_id": tenant_id,
                    "active_memberships": int(
                        membership_counts.get(tenant_id, 0)
                    ),
                    "units": int(unit_counts.get(tenant_id, 0)),
                }
                for tenant_id in tenant_ids
            ],
            "summary": {
                "customers": len(customers),
                "internal_test_customers": sum(
                    row.account_class == "internal_test" for row in customers
                ),
                "active_trials": sum(
                    row.status == "active"
                    and row.ends_at is not None
                    and _after(row.ends_at, instante)
                    for row in trials
                ),
                "active_subscriptions": sum(
                    row.status == "active" for row in subscriptions
                ),
                "past_due_subscriptions": sum(
                    row.status == "past_due" for row in subscriptions
                ),
                "suspended_subscriptions": sum(
                    row.status == "suspended" for row in subscriptions
                ),
                "users": sum(int(value) for value in membership_counts.values()),
                "units": sum(int(value) for value in unit_counts.values()),
            },
            "facts": facts,
            "coverage": {
                "mrr": "pending_governed_semantics",
                "arr": "pending_governed_semantics",
                "churn": "pending_governed_semantics",
                "organization_users_units": "safe_counts_only",
                "health_costs_support": "owned_by_dedicated_sources",
            },
        }

    @staticmethod
    def _catalog_snapshot(repo, instante: datetime) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for plan in repo.listar_planos(product_code="KORDENA"):
            version = repo.versao_efetiva_plano(
                plan_id=plan.plan_id,
                instante=instante,
            )
            prices = (
                repo.listar_precos_versao(
                    plan_version_id=version.plan_version_id
                )
                if version is not None
                else ()
            )
            result.append(
                {
                    "plan_id": plan.plan_id,
                    "plan_code": plan.plan_code,
                    "rank": plan.rank,
                    "status": plan.status.value,
                    "version": plan.version,
                    "effective_version": (
                        {
                            "plan_version_id": version.plan_version_id,
                            "version_number": version.version_number,
                            "display_name": version.display_name,
                            "description": version.description,
                            "trial_eligible": version.trial_eligible,
                            "marketing_badge": version.marketing_badge,
                            "status": version.status.value,
                            "valid_from": _iso(version.valid_from),
                            "valid_until": _iso(version.valid_until),
                            "entitlements": [
                                {
                                    "capability_key": item.capability_key,
                                    "enabled": item.enabled,
                                    "limit_value": _decimal(item.limit_value),
                                    "limit_unit": item.limit_unit,
                                    "config": dict(item.config),
                                }
                                for item in version.entitlements
                            ],
                        }
                        if version is not None
                        else None
                    ),
                    "effective_prices": [
                        {
                            "price_id": price.price_id,
                            "revision": price.revision,
                            "currency": price.currency,
                            "billing_period": price.billing_period,
                            "amount": str(price.amount),
                            "change_policy": price.change_policy.value,
                            "status": price.status.value,
                            "valid_from": _iso(price.valid_from),
                            "valid_until": _iso(price.valid_until),
                        }
                        for price in prices
                        if price.status.value == "published"
                        and price.valid_from is not None
                        and _at_or_before(price.valid_from, instante)
                        and (
                            price.valid_until is None
                            or _after(price.valid_until, instante)
                        )
                    ],
                }
            )
        return result

    @staticmethod
    def _facts(
        *,
        customers,
        trials,
        subscriptions,
        transactions,
        entitlements,
    ) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for row in customers:
            facts.append(
                _fact(
                    external_id=f"customer:{row.fm_customer_id}:created",
                    fact_type="customer.created",
                    payload={
                        "fm_customer_id": row.fm_customer_id,
                        "account_class": row.account_class,
                        "status": row.status,
                    },
                    source_timestamp=row.created_at,
                )
            )
        for row in trials:
            if row.started_at is not None:
                facts.append(
                    _fact(
                        external_id=f"trial:{row.trial_id}:started",
                        fact_type="trial.started",
                        payload={
                            "trial_id": row.trial_id,
                            "fm_customer_id": row.fm_customer_id,
                            "product_account_id": row.product_account_id,
                            "tenant_id": row.tenant_id,
                            "plan_code": row.plan_code,
                        },
                        source_timestamp=row.started_at,
                    )
                )
            if row.converted_at is not None:
                facts.append(
                    _fact(
                        external_id=f"trial:{row.trial_id}:converted",
                        fact_type="trial.converted",
                        payload={
                            "trial_id": row.trial_id,
                            "tenant_id": row.tenant_id,
                        },
                        source_timestamp=row.converted_at,
                    )
                )
            if row.status == "expired" and row.ends_at is not None:
                facts.append(
                    _fact(
                        external_id=f"trial:{row.trial_id}:expired",
                        fact_type="trial.expired",
                        payload={
                            "trial_id": row.trial_id,
                            "tenant_id": row.tenant_id,
                        },
                        source_timestamp=row.ends_at,
                    )
                )
        for row in subscriptions:
            if row.activated_at is not None:
                facts.append(
                    _fact(
                        external_id=(
                            f"subscription:{row.subscription_id}:activated"
                        ),
                        fact_type="subscription.activated",
                        payload={
                            "subscription_id": row.subscription_id,
                            "tenant_id": row.tenant_id,
                            "plan_code": row.plan_code,
                            "amount": str(row.contracted_amount),
                            "currency": row.currency,
                            "billing_period": row.billing_period,
                        },
                        source_timestamp=row.activated_at,
                    )
                )
            if row.status == "canceled" and row.canceled_at is not None:
                facts.append(
                    _fact(
                        external_id=(
                            f"subscription:{row.subscription_id}:cancelled"
                        ),
                        fact_type="subscription.cancelled",
                        payload={
                            "subscription_id": row.subscription_id,
                            "tenant_id": row.tenant_id,
                        },
                        source_timestamp=row.canceled_at,
                    )
                )
        for row in transactions:
            timestamp = row.provider_occurred_at or row.updated_at
            if row.transaction_type == "payment" and row.status == "succeeded":
                facts.append(
                    _fact(
                        external_id=(
                            f"billing:{row.billing_transaction_id}:settled"
                        ),
                        fact_type="payment.settled",
                        payload={
                            "billing_transaction_id": (
                                row.billing_transaction_id
                            ),
                            "subscription_id": row.subscription_id,
                            "amount": _decimal(row.amount),
                            "currency": row.currency,
                            "reconciliation_status": (
                                row.reconciliation_status
                            ),
                        },
                        source_timestamp=timestamp,
                    )
                )
            elif row.transaction_type == "payment" and row.status == "failed":
                facts.append(
                    _fact(
                        external_id=(
                            f"billing:{row.billing_transaction_id}:failed"
                        ),
                        fact_type="payment.failed",
                        payload={
                            "billing_transaction_id": (
                                row.billing_transaction_id
                            ),
                            "subscription_id": row.subscription_id,
                            "currency": row.currency,
                        },
                        source_timestamp=timestamp,
                    )
                )
        for row in entitlements:
            facts.append(
                _fact(
                    external_id=(
                        f"entitlement:{row.product_account_id}:{row.revision}"
                    ),
                    fact_type="entitlement.changed",
                    payload={
                        "tenant_id": row.tenant_id,
                        "product_account_id": row.product_account_id,
                        "revision": row.revision,
                        "commercial_state": row.commercial_state,
                        "access_mode": row.access_mode,
                        "plan_code": row.plan_code,
                    },
                    source_timestamp=row.last_synced_at,
                )
            )
        return facts
