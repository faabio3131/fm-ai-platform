from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from application.fmcc_commercial_projection import AplicacaoFMCCCommercialProjectionV1

NOW = datetime(2026, 9, 23, 16, 0, tzinfo=timezone.utc)


def test_internal_test_accounts_are_excluded_from_commercial_metric_facts() -> None:
    customers = (
        SimpleNamespace(
            fm_customer_id="customer-real",
            account_class="trial",
            status="active",
            created_at=NOW,
        ),
        SimpleNamespace(
            fm_customer_id="customer-internal",
            account_class="internal_test",
            status="active",
            created_at=NOW,
        ),
    )
    accounts = (
        SimpleNamespace(
            product_account_id="account-real",
            fm_customer_id="customer-real",
        ),
        SimpleNamespace(
            product_account_id="account-internal",
            fm_customer_id="customer-internal",
        ),
    )
    trials = (
        SimpleNamespace(
            trial_id="trial-real",
            fm_customer_id="customer-real",
            product_account_id="account-real",
            tenant_id="tenant-real",
            plan_code="KORDENA_PLAN_A",
            started_at=NOW,
            converted_at=None,
            status="active",
            ends_at=NOW,
        ),
        SimpleNamespace(
            trial_id="trial-internal",
            fm_customer_id="customer-internal",
            product_account_id="account-internal",
            tenant_id="tenant-internal",
            plan_code="KORDENA_PLAN_A",
            started_at=NOW,
            converted_at=None,
            status="active",
            ends_at=NOW,
        ),
    )

    facts = AplicacaoFMCCCommercialProjectionV1._facts(
        customers=customers,
        accounts=accounts,
        trials=trials,
        subscriptions=(),
        transactions=(),
        entitlements=(),
    )

    serialized = str(facts)
    assert "customer-real" in serialized
    assert "trial-real" in serialized
    assert "customer-internal" not in serialized
    assert "trial-internal" not in serialized


def test_internal_test_accounts_are_excluded_from_commercial_summary() -> None:
    customers = (
        SimpleNamespace(
            fm_customer_id="customer-real",
            account_class="trial",
        ),
        SimpleNamespace(
            fm_customer_id="customer-internal",
            account_class="internal_test",
        ),
    )
    accounts = (
        SimpleNamespace(
            product_account_id="account-real",
            fm_customer_id="customer-real",
            product_tenant_id="tenant-real",
        ),
        SimpleNamespace(
            product_account_id="account-internal",
            fm_customer_id="customer-internal",
            product_tenant_id="tenant-internal",
        ),
    )
    trials = (
        SimpleNamespace(
            fm_customer_id="customer-real",
            status="active",
            ends_at=datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            fm_customer_id="customer-internal",
            status="active",
            ends_at=datetime(2026, 9, 24, 16, 0, tzinfo=timezone.utc),
        ),
    )
    subscriptions = (
        SimpleNamespace(
            subscription_id="subscription-real",
            fm_customer_id="customer-real",
            status="active",
        ),
        SimpleNamespace(
            subscription_id="subscription-internal",
            fm_customer_id="customer-internal",
            status="past_due",
        ),
    )
    transactions = (
        SimpleNamespace(
            subscription_id="subscription-real",
            transaction_type="payment",
            status="failed",
            reconciliation_status="pending",
        ),
        SimpleNamespace(
            subscription_id="subscription-internal",
            transaction_type="payment",
            status="succeeded",
            reconciliation_status="in_sync",
        ),
    )

    summary = AplicacaoFMCCCommercialProjectionV1._summary(
        customers=customers,
        accounts=accounts,
        trials=trials,
        subscriptions=subscriptions,
        transactions=transactions,
        membership_counts={"tenant-real": 3, "tenant-internal": 99},
        unit_counts={"tenant-real": 2, "tenant-internal": 88},
        instante=NOW,
    )

    assert summary == {
        "customers": 1,
        "internal_test_customers": 1,
        "active_trials": 1,
        "active_subscriptions": 1,
        "past_due_subscriptions": 0,
        "suspended_subscriptions": 0,
        "confirmed_payments": 0,
        "failed_payments": 1,
        "reconciled_transactions": 0,
        "users": 3,
        "units": 2,
    }
