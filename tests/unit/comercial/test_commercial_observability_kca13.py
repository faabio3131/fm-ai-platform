from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from application.commercial_observability import AplicacaoCommercialObservabilityKCA13

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
