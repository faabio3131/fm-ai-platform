from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from core.comercial.billing_events import (
    BillingCanonicalEventType,
    BillingTransactionStatus,
    NormalizedBillingEvent,
    is_out_of_order,
    transaction_status_for_event,
)
from core.comercial.erros import DadoComercialInvalido


NOW = datetime(2026, 9, 22, 21, 30, tzinfo=timezone.utc)


def test_transaction_event_requires_external_transaction_ref() -> None:
    with pytest.raises(
        DadoComercialInvalido,
        match="transaction_ref_obrigatoria",
    ):
        NormalizedBillingEvent(
            provider_code="provider_x",
            external_event_id="evt-1",
            canonical_event_type=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
            occurred_at=NOW,
        )


def test_subscription_event_requires_external_subscription_ref() -> None:
    with pytest.raises(
        DadoComercialInvalido,
        match="subscription_ref_obrigatoria",
    ):
        NormalizedBillingEvent(
            provider_code="provider_x",
            external_event_id="evt-2",
            canonical_event_type=BillingCanonicalEventType.SUBSCRIPTION_CANCELED,
            occurred_at=NOW,
        )


def test_renewal_requires_complete_valid_period() -> None:
    with pytest.raises(DadoComercialInvalido, match="renewal_period_obrigatorio"):
        NormalizedBillingEvent(
            provider_code="provider_x",
            external_event_id="evt-3",
            canonical_event_type=BillingCanonicalEventType.SUBSCRIPTION_RENEWED,
            occurred_at=NOW,
            external_subscription_ref="sub-ext-1",
        )

    event = NormalizedBillingEvent(
        provider_code="provider_x",
        external_event_id="evt-4",
        canonical_event_type=BillingCanonicalEventType.SUBSCRIPTION_RENEWED,
        occurred_at=NOW,
        external_subscription_ref="sub-ext-1",
        period_start=NOW,
        period_end=NOW + timedelta(days=30),
    )
    assert event.provider_code == "PROVIDER_X"
    assert event.period_end is not None


def test_ordering_prefers_provider_sequence_when_both_exist() -> None:
    assert (
        is_out_of_order(
            incoming_sequence=9,
            incoming_occurred_at=NOW + timedelta(hours=1),
            last_sequence=10,
            last_occurred_at=NOW,
        )
        is True
    )
    assert (
        is_out_of_order(
            incoming_sequence=11,
            incoming_occurred_at=NOW - timedelta(hours=1),
            last_sequence=10,
            last_occurred_at=NOW,
        )
        is False
    )


def test_ordering_falls_back_to_provider_occurred_at() -> None:
    assert (
        is_out_of_order(
            incoming_sequence=None,
            incoming_occurred_at=NOW,
            last_sequence=None,
            last_occurred_at=NOW + timedelta(seconds=1),
        )
        is True
    )


def test_payment_event_status_is_canonical() -> None:
    assert (
        transaction_status_for_event(
            BillingCanonicalEventType.PAYMENT_SUCCEEDED
        )
        == BillingTransactionStatus.SUCCEEDED
    )
    event = NormalizedBillingEvent(
        provider_code="provider_x",
        external_event_id="evt-5",
        canonical_event_type=BillingCanonicalEventType.PAYMENT_SUCCEEDED,
        occurred_at=NOW,
        external_transaction_ref="tx-1",
        amount=Decimal("99.90"),
        currency="brl",
    )
    assert event.currency == "BRL"
