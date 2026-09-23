from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from application.commercial_observability import AplicacaoCommercialObservabilityKCA13
from infra.comercial.modelos_orm import FMCustomerORM, FMProductAccountORM
from infra.comercial.subscription_orm import FMCommercialSubscriptionORM
from infra.comercial.trial_orm import FMCommercialTrialORM
from migrations.runner import run_migrations

NOW = datetime(2026, 9, 23, 18, 0, tzinfo=timezone.utc)
START = NOW - timedelta(days=30)


def _subscription(
    *,
    subscription_id: str,
    status: str = "active",
    amount: str = "100.00",
    currency: str = "BRL",
    billing_period: str = "MONTHLY",
):
    return SimpleNamespace(
        subscription_id=subscription_id,
        status=status,
        contracted_amount=Decimal(amount),
        currency=currency,
        billing_period=billing_period,
    )


def test_kca13_mrr_arr_keep_currencies_separate_and_report_unknown_periods() -> None:
    metrics = AplicacaoCommercialObservabilityKCA13._metrics(
        now=NOW,
        window_start=START,
        expiring_until=NOW + timedelta(days=7),
        signups=(),
        provisioning=(),
        trials=(),
        subscriptions=(
            _subscription(subscription_id="monthly-brl", amount="120.00"),
            _subscription(
                subscription_id="annual-usd",
                amount="1200.00",
                currency="USD",
                billing_period="ANNUAL",
            ),
            _subscription(
                subscription_id="custom-brl",
                amount="50.00",
                billing_period="WEEKLY",
            ),
        ),
        transactions=(),
        subscription_events=(),
        customer_ids=set(),
    )

    assert metrics["mrr"]["status"] == "partial"
    assert metrics["mrr"]["quality_status"] == "partial"
    assert metrics["mrr"]["value"]["by_currency"] == [
        {"currency": "BRL", "amount": "120.00"},
        {"currency": "USD", "amount": "100.00"},
    ]
    assert metrics["arr"]["value"]["by_currency"] == [
        {"currency": "BRL", "amount": "1440.00"},
        {"currency": "USD", "amount": "1200.00"},
    ]
    assert metrics["mrr"]["value"]["unsupported_active_periods"] == {"WEEKLY": 1}


def test_kca13_conversion_rate_is_unavailable_for_empty_cohort_not_zero() -> None:
    metrics = AplicacaoCommercialObservabilityKCA13._metrics(
        now=NOW,
        window_start=START,
        expiring_until=NOW + timedelta(days=7),
        signups=(),
        provisioning=(),
        trials=(),
        subscriptions=(),
        transactions=(),
        subscription_events=(),
        customer_ids=set(),
    )

    assert metrics["conversion_rate"]["status"] == "unavailable"
    assert metrics["conversion_rate"]["value"] is None
    assert metrics["conversion_rate"]["quality_status"] == "missing"


def test_kca13_churn_reconstructs_starting_active_base_from_outbox() -> None:
    events = (
        SimpleNamespace(
            aggregate_id="sub-a",
            event_type="subscription.activated",
            occurred_at=START - timedelta(days=2),
            payload={"status": "active"},
        ),
        SimpleNamespace(
            aggregate_id="sub-b",
            event_type="subscription.activated",
            occurred_at=START - timedelta(days=1),
            payload={"status": "active"},
        ),
        SimpleNamespace(
            aggregate_id="sub-a",
            event_type="subscription.canceled",
            occurred_at=START + timedelta(days=4),
            payload={"status": "canceled"},
        ),
    )

    result = AplicacaoCommercialObservabilityKCA13._churn(
        now=NOW,
        window_start=START,
        subscription_events=events,
    )

    assert result == {
        "status": "available",
        "value": "50.00",
        "quality_status": "reconciled",
    }


def test_kca13_finops_never_invents_infrastructure_cost() -> None:
    rows = (
        SimpleNamespace(
            tenant_id="tenant-real",
            moeda="BRL",
            cost_total=Decimal("2.50"),
            cost_known_events=2,
            cost_unknown_events=0,
            attempts=3,
            input_tokens=100,
            output_tokens=50,
            cached_tokens=10,
        ),
    )
    entitlements = (
        SimpleNamespace(tenant_id="tenant-real", plan_code="KORDENA_PLAN_A"),
    )

    result = AplicacaoCommercialObservabilityKCA13._finops(
        now=NOW,
        rows=rows,
        entitlements=entitlements,
    )

    assert result["ai_cost_per_tenant"]["status"] == "available"
    assert result["ai_cost_per_tenant"]["tenants"][0]["costs"] == [
        {"currency": "BRL", "amount": "2.50"}
    ]
    assert result["infra_cost_per_tenant"]["status"] == "unavailable"
    assert result["infra_cost_per_tenant"]["tenants"] is None
    assert (
        result["infra_cost_per_tenant"]["reason"]
        == "infrastructure_cost_source_not_configured"
    )


def test_kca13_alerts_are_deterministic_failure_signals_without_risk_score() -> None:
    alerts = AplicacaoCommercialObservabilityKCA13._alerts(
        antiabuse={
            "repeated_trial_customers": 1,
        },
        health={
            "stale_entitlements": 2,
            "webhook_dead_letters_30d": 1,
            "webhook_failed_retryable_30d": 0,
            "provisioning_failed_retryable_30d": 0,
            "ai_cost_unknown_events_30d": 0,
        },
    )

    assert {item["code"] for item in alerts} == {
        "kca13.entitlement.stale",
        "kca13.webhook.dead_letter",
        "kca13.trial.repeated_customer",
    }
    assert all(item["count"] > 0 for item in alerts)


def test_kca13_snapshot_does_not_mix_other_product_trials_or_subscriptions() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    with factory() as session, session.begin():
        session.add(
            FMCustomerORM(
                fm_customer_id="customer-multi-product",
                customer_code="KRD-C-999991",
                display_name="Multi Product",
                legal_name=None,
                status="active",
                account_class="paid",
                primary_contact_email="multi@example.test",
                primary_contact_phone=None,
                created_by="test",
                updated_by="test",
                version=1,
                created_at=NOW - timedelta(days=60),
                updated_at=NOW,
            )
        )
        session.add_all(
            [
                FMProductAccountORM(
                    product_account_id="account-kordena",
                    fm_customer_id="customer-multi-product",
                    product_code="KORDENA",
                    product_tenant_id="tenant-kordena",
                    status="active",
                    created_by="test",
                    updated_by="test",
                    version=1,
                    created_at=NOW - timedelta(days=60),
                    updated_at=NOW,
                    activated_at=NOW - timedelta(days=60),
                    suspended_at=None,
                    closed_at=None,
                ),
                FMProductAccountORM(
                    product_account_id="account-iron",
                    fm_customer_id="customer-multi-product",
                    product_code="IRON",
                    product_tenant_id="tenant-iron",
                    status="active",
                    created_by="test",
                    updated_by="test",
                    version=1,
                    created_at=NOW - timedelta(days=60),
                    updated_at=NOW,
                    activated_at=NOW - timedelta(days=60),
                    suspended_at=None,
                    closed_at=None,
                ),
            ]
        )
        session.add_all(
            [
                FMCommercialTrialORM(
                    trial_id="trial-kordena",
                    fm_customer_id="customer-multi-product",
                    product_account_id="account-kordena",
                    tenant_id="tenant-kordena",
                    plan_code="KORDENA_PLAN_A",
                    plan_version_id="kordena-plan-v1",
                    status="active",
                    policy_version="v1",
                    duration_days=30,
                    started_at=NOW - timedelta(days=2),
                    ends_at=NOW + timedelta(days=28),
                    converted_at=None,
                    revoked_at=None,
                    override_reason=None,
                    version=1,
                    correlation_id="corr-kordena",
                    created_at=NOW - timedelta(days=2),
                    updated_at=NOW,
                ),
                FMCommercialTrialORM(
                    trial_id="trial-iron",
                    fm_customer_id="customer-multi-product",
                    product_account_id="account-iron",
                    tenant_id="tenant-iron",
                    plan_code="IRON_PLAN_A",
                    plan_version_id="iron-plan-v1",
                    status="active",
                    policy_version="v1",
                    duration_days=30,
                    started_at=NOW - timedelta(days=2),
                    ends_at=NOW + timedelta(days=28),
                    converted_at=None,
                    revoked_at=None,
                    override_reason=None,
                    version=1,
                    correlation_id="corr-iron",
                    created_at=NOW - timedelta(days=2),
                    updated_at=NOW,
                ),
            ]
        )
        session.add_all(
            [
                FMCommercialSubscriptionORM(
                    subscription_id="sub-kordena",
                    fm_customer_id="customer-multi-product",
                    product_account_id="account-kordena",
                    tenant_id="tenant-kordena",
                    plan_code="KORDENA_PLAN_A",
                    plan_version_id="kordena-plan-v1",
                    price_id="kordena-price",
                    currency="BRL",
                    billing_period="monthly",
                    contracted_amount=Decimal("100.00"),
                    status="active",
                    current_period_start=NOW - timedelta(days=1),
                    current_period_end=NOW + timedelta(days=29),
                    cancel_at_period_end=False,
                    canceled_at=None,
                    activated_at=NOW - timedelta(days=1),
                    suspended_at=None,
                    version=1,
                    correlation_id="corr-kordena",
                    created_at=NOW - timedelta(days=1),
                    updated_at=NOW,
                ),
                FMCommercialSubscriptionORM(
                    subscription_id="sub-iron",
                    fm_customer_id="customer-multi-product",
                    product_account_id="account-iron",
                    tenant_id="tenant-iron",
                    plan_code="IRON_PLAN_A",
                    plan_version_id="iron-plan-v1",
                    price_id="iron-price",
                    currency="BRL",
                    billing_period="monthly",
                    contracted_amount=Decimal("999.00"),
                    status="active",
                    current_period_start=NOW - timedelta(days=1),
                    current_period_end=NOW + timedelta(days=29),
                    cancel_at_period_end=False,
                    canceled_at=None,
                    activated_at=NOW - timedelta(days=1),
                    suspended_at=None,
                    version=1,
                    correlation_id="corr-iron",
                    created_at=NOW - timedelta(days=1),
                    updated_at=NOW,
                ),
            ]
        )

    result = AplicacaoCommercialObservabilityKCA13(factory).snapshot(agora=NOW)

    assert result["metrics"]["trial_active"]["value"] == 1
    assert result["metrics"]["subscription_active"]["value"] == 1
    assert result["metrics"]["mrr"]["value"]["by_currency"] == [
        {"currency": "BRL", "amount": "100.00"}
    ]
