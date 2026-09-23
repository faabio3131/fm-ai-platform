"""Domínio provider-neutral de eventos de billing — KCA-10."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from core.comercial.erros import DadoComercialInvalido


class BillingCanonicalEventType(StrEnum):
    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_REFUNDED = "payment_refunded"
    SUBSCRIPTION_ACTIVE = "subscription_active"
    SUBSCRIPTION_PAST_DUE = "subscription_past_due"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended"
    SUBSCRIPTION_CANCELED = "subscription_canceled"
    SUBSCRIPTION_RENEWED = "subscription_renewed"


class BillingTransactionStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class BillingTransactionType(StrEnum):
    PAYMENT = "payment"
    REFUND = "refund"


class BillingWebhookInboxStatus(StrEnum):
    RECEIVED = "received"
    VERIFIED = "verified"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED_RETRYABLE = "failed_retryable"
    DEAD_LETTER = "dead_letter"
    IGNORED_OUT_OF_ORDER = "ignored_out_of_order"
    REJECTED = "rejected"


class BillingReconciliationStatus(StrEnum):
    NOT_CHECKED = "not_checked"
    IN_SYNC = "in_sync"
    REPAIRED = "repaired"
    FAILED = "failed"


@dataclass(frozen=True, kw_only=True)
class NormalizedBillingEvent:
    provider_code: str
    external_event_id: str
    canonical_event_type: BillingCanonicalEventType
    occurred_at: datetime
    provider_sequence: int | None = None
    external_subscription_ref: str | None = None
    external_transaction_ref: str | None = None
    transaction_type: BillingTransactionType | None = None
    transaction_status: BillingTransactionStatus | None = None
    amount: Decimal | None = None
    currency: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    metadata_safe: dict[str, object] | None = None

    def __post_init__(self) -> None:
        provider = self.provider_code.strip().upper()
        event_id = self.external_event_id.strip()
        if not provider or len(provider) > 64:
            raise DadoComercialInvalido("billing_event_provider_code_invalido")
        if not event_id or len(event_id) > 255:
            raise DadoComercialInvalido("billing_external_event_id_invalido")
        occurred = self.occurred_at
        if occurred.tzinfo is None or occurred.utcoffset() is None:
            raise DadoComercialInvalido("billing_event_datetime_sem_timezone")
        if self.provider_sequence is not None and self.provider_sequence < 0:
            raise DadoComercialInvalido("billing_provider_sequence_invalida")
        if (
            self.external_transaction_ref is not None
            and not self.external_transaction_ref.strip()
        ):
            raise DadoComercialInvalido(
                "billing_external_transaction_ref_invalida"
            )
        if (
            self.external_subscription_ref is not None
            and not self.external_subscription_ref.strip()
        ):
            raise DadoComercialInvalido(
                "billing_external_subscription_ref_invalida"
            )
        if self.amount is not None and self.amount < 0:
            raise DadoComercialInvalido("billing_transaction_amount_invalido")
        if self.currency is not None:
            currency = self.currency.strip().upper()
            if len(currency) != 3:
                raise DadoComercialInvalido("billing_currency_invalida")
            object.__setattr__(self, "currency", currency)
        if (self.period_start is None) != (self.period_end is None):
            raise DadoComercialInvalido("billing_periodo_incompleto")
        if self.period_start is not None and self.period_end is not None:
            start = _utc(self.period_start)
            end = _utc(self.period_end)
            if end <= start:
                raise DadoComercialInvalido("billing_periodo_invalido")
            object.__setattr__(self, "period_start", start)
            object.__setattr__(self, "period_end", end)
        object.__setattr__(self, "provider_code", provider)
        object.__setattr__(self, "external_event_id", event_id)
        object.__setattr__(self, "occurred_at", _utc(occurred))
        if self.external_subscription_ref is not None:
            object.__setattr__(
                self,
                "external_subscription_ref",
                self.external_subscription_ref.strip(),
            )
        if self.external_transaction_ref is not None:
            object.__setattr__(
                self,
                "external_transaction_ref",
                self.external_transaction_ref.strip(),
            )
        transaction_events = {
            BillingCanonicalEventType.PAYMENT_SUCCEEDED,
            BillingCanonicalEventType.PAYMENT_FAILED,
            BillingCanonicalEventType.PAYMENT_REFUNDED,
        }
        subscription_events = {
            BillingCanonicalEventType.SUBSCRIPTION_ACTIVE,
            BillingCanonicalEventType.SUBSCRIPTION_PAST_DUE,
            BillingCanonicalEventType.SUBSCRIPTION_SUSPENDED,
            BillingCanonicalEventType.SUBSCRIPTION_CANCELED,
            BillingCanonicalEventType.SUBSCRIPTION_RENEWED,
        }
        if self.canonical_event_type in transaction_events:
            if self.external_transaction_ref is None:
                raise DadoComercialInvalido(
                    "billing_event_transaction_ref_obrigatoria"
                )
            expected_status = transaction_status_for_event(
                self.canonical_event_type
            )
            if (
                self.transaction_status is not None
                and expected_status is not None
                and self.transaction_status != expected_status
            ):
                raise DadoComercialInvalido(
                    "billing_event_transaction_status_incompativel"
                )
        if (
            self.canonical_event_type in subscription_events
            and self.external_subscription_ref is None
        ):
            raise DadoComercialInvalido(
                "billing_event_subscription_ref_obrigatoria"
            )
        if (
            self.canonical_event_type
            == BillingCanonicalEventType.SUBSCRIPTION_RENEWED
            and (self.period_start is None or self.period_end is None)
        ):
            raise DadoComercialInvalido(
                "billing_event_renewal_period_obrigatorio"
            )
        object.__setattr__(self, "metadata_safe", dict(self.metadata_safe or {}))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DadoComercialInvalido("billing_event_datetime_sem_timezone")
    return value.astimezone(timezone.utc)


def is_out_of_order(
    *,
    incoming_sequence: int | None,
    incoming_occurred_at: datetime,
    last_sequence: int | None,
    last_occurred_at: datetime | None,
) -> bool:
    incoming_time = _utc(incoming_occurred_at)
    if incoming_sequence is not None and last_sequence is not None:
        return incoming_sequence <= last_sequence
    if last_occurred_at is not None:
        return incoming_time <= _utc(last_occurred_at)
    return False


def transaction_status_for_event(
    event_type: BillingCanonicalEventType,
) -> BillingTransactionStatus | None:
    return {
        BillingCanonicalEventType.PAYMENT_SUCCEEDED: BillingTransactionStatus.SUCCEEDED,
        BillingCanonicalEventType.PAYMENT_FAILED: BillingTransactionStatus.FAILED,
        BillingCanonicalEventType.PAYMENT_REFUNDED: BillingTransactionStatus.REFUNDED,
    }.get(event_type)
