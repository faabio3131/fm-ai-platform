from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from core.comercial.billing import (
    BillingAuthenticationError,
    BillingCallContext,
    BillingProviderUnavailable,
    BillingRateLimited,
    BillingSubscriptionChangeRequest,
    BillingTransactionNotFound,
    BillingValidationError,
    BillingWebhookInvalid,
    CheckoutRequest,
    WebhookVerificationResult,
)
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    BillingTransactionStatus,
)
from core.seguranca.segredos import SecretValue
from infra.comercial.mercado_pago_subscriptions import (
    MercadoPagoSubscriptionsBillingProvider,
)

ROOT = Path(__file__).resolve().parents[3]
FRONTEND_APP = ROOT / "http_api" / "frontend_app.py"

ACCESS_TOKEN = "TEST-credential-value-only-for-unit-tests"
WEBHOOK_SECRET = "webhook-unit-test-secret"


class Response:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeHTTP:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses: list[Response | BaseException] = []

    def push(self, status_code: int, payload: Any) -> None:
        self.responses.append(Response(status_code, payload))

    def push_error(self, error: BaseException) -> None:
        self.responses.append(error)

    def request(
        self,
        method: str,
        url: str,
        *,
        headers,
        json,
        timeout: float,
    ):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers),
                "json": json,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("fake response missing")
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


def _credential() -> SecretValue:
    return SecretValue(
        json.dumps(
            {
                "access_token": ACCESS_TOKEN,
                "webhook_secret": WEBHOOK_SECRET,
            }
        )
    )


def _context(key: str = "idem") -> BillingCallContext:
    return BillingCallContext(
        idempotency_key=key,
        correlation_id=f"corr-{key}",
        timeout_seconds=8.0,
    )


def _checkout() -> CheckoutRequest:
    return CheckoutRequest(
        fm_customer_id="customer-fm-1",
        product_account_id="product-account-1",
        price_id="price-1",
        subscription_id="subscription-internal-1",
        success_url="https://kordenaia.com.br/assinatura/sucesso",
        cancel_url="https://kordenaia.com.br/assinatura/cancelada",
        contact_email="cliente@example.com",
        amount=Decimal("99.90"),
        currency="BRL",
        billing_period="MONTHLY",
        description="Kordena Plano A",
    )


def _signed_payload(
    *,
    event_type: str,
    resource_id: str,
    request_id: str = "request-1",
    ts: str = "1770000000000",
) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(
        {
            "id": "notification-1",
            "type": event_type,
            "data": {"id": resource_id},
        },
        separators=(",", ":"),
    ).encode()
    manifest = f"id:{resource_id};request-id:{request_id};ts:{ts};"
    signature = hmac.new(
        WEBHOOK_SECRET.encode(),
        manifest.encode(),
        hashlib.sha256,
    ).hexdigest()
    return body, {
        "x-request-id": request_id,
        "x-signature": f"ts={ts},v1={signature}",
    }


def test_connection_is_read_only_and_secret_is_not_exposed() -> None:
    http = FakeHTTP()
    http.push(200, {"id": 123456})
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    result = provider.test_connection(
        context=_context("connection"),
        credential=_credential(),
    )

    assert result.ok is True
    assert result.provider_code == "MERCADO_PAGO_SUBSCRIPTIONS"
    assert http.calls == [
        {
            "method": "GET",
            "url": "https://api.mercadolibre.com/users/me",
            "headers": {
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            "json": None,
            "timeout": 8.0,
        }
    ]
    assert ACCESS_TOKEN not in repr(_credential())


def test_checkout_uses_canonical_snapshot_and_returns_preapproval_link() -> None:
    http = FakeHTTP()
    http.push(
        201,
        {
            "id": "preapproval-1",
            "init_point": "https://www.mercadopago.com/subscriptions/checkout/test",
        },
    )
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    result = provider.create_checkout(
        request=_checkout(),
        context=_context("checkout-idempotency"),
        credential=_credential(),
    )

    assert result.external_subscription_ref == "preapproval-1"
    assert result.external_checkout_ref == "preapproval-1"
    assert result.checkout_url.startswith("https://www.mercadopago.com/")
    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://api.mercadopago.com/preapproval"
    assert call["headers"]["X-Idempotency-Key"] == "checkout-idempotency"
    assert call["json"] == {
        "reason": "Kordena Plano A",
        "external_reference": "subscription-internal-1",
        "payer_email": "cliente@example.com",
        "auto_recurring": {
            "frequency": 1,
            "frequency_type": "months",
            "transaction_amount": 99.9,
            "currency_id": "BRL",
        },
        "back_url": "https://kordenaia.com.br/assinatura/sucesso",
        "status": "pending",
    }


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("MONTHLY", (1, "months")),
        ("MENSAL", (1, "months")),
        ("QUARTERLY", (3, "months")),
        ("SEMESTRAL", (6, "months")),
        ("ANNUAL", (12, "months")),
    ],
)
def test_checkout_maps_supported_periods(period: str, expected: tuple[int, str]) -> None:
    request = _checkout()
    request = CheckoutRequest(
        **{
            **request.__dict__,
            "billing_period": period,
        }
    )
    http = FakeHTTP()
    http.push(201, {"id": "preapproval-1", "init_point": "https://example.test"})
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    provider.create_checkout(
        request=request,
        context=_context(period),
        credential=_credential(),
    )

    recurrence = http.calls[0]["json"]["auto_recurring"]
    assert (recurrence["frequency"], recurrence["frequency_type"]) == expected


def test_unsupported_period_fails_closed_before_network() -> None:
    request = _checkout()
    request = CheckoutRequest(
        **{
            **request.__dict__,
            "billing_period": "EVERY_FORTNIGHT_CUSTOM",
        }
    )
    http = FakeHTTP()
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    with pytest.raises(BillingValidationError, match="period_not_supported"):
        provider.create_checkout(
            request=request,
            context=_context(),
            credential=_credential(),
        )

    assert http.calls == []


def test_cancel_and_change_subscription_are_idempotent_mutations() -> None:
    http = FakeHTTP()
    http.push(200, {"id": "preapproval-1", "payer_id": "payer-1"})
    http.push(200, {"id": "preapproval-1", "payer_id": "payer-1"})
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    canceled = provider.cancel_subscription(
        external_subscription_ref="preapproval-1",
        context=_context("cancel-key"),
        credential=_credential(),
    )
    changed = provider.change_subscription(
        request=BillingSubscriptionChangeRequest(
            external_subscription_ref="preapproval-1",
            price_id="price-2",
            amount=Decimal("119.90"),
            currency="BRL",
            billing_period="MONTHLY",
        ),
        context=_context("change-key"),
        credential=_credential(),
    )

    assert canceled.external_subscription_ref == "preapproval-1"
    assert changed.external_subscription_ref == "preapproval-1"
    assert http.calls[0]["json"] == {"status": "canceled"}
    assert http.calls[0]["headers"]["X-Idempotency-Key"] == "cancel-key"
    assert http.calls[1]["json"] == {
        "auto_recurring": {
            "transaction_amount": 119.9,
            "currency_id": "BRL",
            "frequency": 1,
            "frequency_type": "months",
        }
    }
    assert http.calls[1]["headers"]["X-Idempotency-Key"] == "change-key"


@pytest.mark.parametrize(
    ("payment_status", "expected"),
    [
        ("approved", BillingTransactionStatus.SUCCEEDED.value),
        ("rejected", BillingTransactionStatus.FAILED.value),
        ("refunded", BillingTransactionStatus.REFUNDED.value),
        ("pending", BillingTransactionStatus.PENDING.value),
    ],
)
def test_fetch_transaction_maps_authorized_payment(
    payment_status: str,
    expected: str,
) -> None:
    http = FakeHTTP()
    http.push(
        200,
        {
            "id": 6114264375,
            "currency_id": "BRL",
            "transaction_amount": "24.50",
            "status": "scheduled",
            "summarized": "pending",
            "payment": {"id": 19951521071, "status": payment_status},
        },
    )
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    result = provider.fetch_transaction(
        external_transaction_ref="6114264375",
        context=_context("fetch"),
        credential=_credential(),
    )

    assert result.amount == Decimal("24.50")
    assert result.currency == "BRL"
    assert result.status == expected
    assert "X-Idempotency-Key" not in http.calls[0]["headers"]


def test_webhook_signature_and_subscription_normalization() -> None:
    body, headers = _signed_payload(
        event_type="subscription_preapproval",
        resource_id="preapproval-1",
    )
    http = FakeHTTP()
    http.push(
        200,
        {
            "id": "preapproval-1",
            "version": 4,
            "status": "authorized",
            "last_modified": "2026-10-02T20:00:00-03:00",
        },
    )
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    verification = provider.verify_webhook(
        payload=body,
        headers=headers,
        context=_context("verify"),
        credential=_credential(),
    )
    event = provider.normalize_webhook(
        payload=body,
        verification=verification,
        context=_context("normalize"),
        credential=_credential(),
    )

    assert verification.valid is True
    assert event.canonical_event_type == BillingCanonicalEventType.SUBSCRIPTION_ACTIVE
    assert event.external_subscription_ref == "preapproval-1"
    assert event.provider_sequence == 4
    assert event.occurred_at == datetime(
        2026, 10, 2, 23, 0, 0, tzinfo=timezone.utc
    )


def test_webhook_authorized_payment_is_normalized_without_trusting_body_amount() -> None:
    body, headers = _signed_payload(
        event_type="subscription_authorized_payment",
        resource_id="6114264375",
    )
    http = FakeHTTP()
    http.push(
        200,
        {
            "id": 6114264375,
            "preapproval_id": "preapproval-1",
            "currency_id": "BRL",
            "transaction_amount": "24.50",
            "last_modified": "2026-10-02T20:00:00-03:00",
            "payment": {"id": 19951521071, "status": "approved"},
        },
    )
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    verification = provider.verify_webhook(
        payload=body,
        headers=headers,
        context=_context("verify-payment"),
        credential=_credential(),
    )
    event = provider.normalize_webhook(
        payload=body,
        verification=verification,
        context=_context("normalize-payment"),
        credential=_credential(),
    )

    assert event.canonical_event_type == BillingCanonicalEventType.PAYMENT_SUCCEEDED
    assert event.transaction_status == BillingTransactionStatus.SUCCEEDED
    assert event.external_transaction_ref == "6114264375"
    assert event.external_subscription_ref == "preapproval-1"
    assert event.amount == Decimal("24.50")
    assert event.currency == "BRL"
    assert http.calls[0]["url"].endswith("/authorized_payments/6114264375")


def test_forged_webhook_is_rejected_without_provider_lookup() -> None:
    body, headers = _signed_payload(
        event_type="subscription_preapproval",
        resource_id="preapproval-1",
    )
    headers["x-signature"] = "ts=1770000000000,v1=forged"
    http = FakeHTTP()
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    verification = provider.verify_webhook(
        payload=body,
        headers=headers,
        context=_context("forged"),
        credential=_credential(),
    )

    assert verification.valid is False
    with pytest.raises(BillingWebhookInvalid, match="signature_invalid"):
        provider.normalize_webhook(
            payload=body,
            verification=verification,
            context=_context("forged-normalize"),
            credential=_credential(),
        )
    assert http.calls == []


@pytest.mark.parametrize(
    ("status_code", "error"),
    [
        (401, BillingAuthenticationError),
        (429, BillingRateLimited),
        (503, BillingProviderUnavailable),
        (422, BillingValidationError),
    ],
)
def test_provider_http_failures_map_to_canonical_errors(
    status_code: int,
    error: type[Exception],
) -> None:
    http = FakeHTTP()
    http.push(status_code, {"message": "sanitized"})
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    with pytest.raises(error):
        provider.test_connection(
            context=_context("error"),
            credential=_credential(),
        )


def test_transaction_404_has_specific_canonical_error() -> None:
    http = FakeHTTP()
    http.push(404, {"message": "not found"})
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    with pytest.raises(BillingTransactionNotFound):
        provider.fetch_transaction(
            external_transaction_ref="missing",
            context=_context("missing"),
            credential=_credential(),
        )


def test_network_timeout_is_retryable_provider_error() -> None:
    request = httpx.Request("GET", "https://api.mercadolibre.com/users/me")
    http = FakeHTTP()
    http.push_error(httpx.ReadTimeout("timeout", request=request))
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    with pytest.raises(Exception) as caught:
        provider.test_connection(
            context=_context("timeout"),
            credential=_credential(),
        )
    assert getattr(caught.value, "retryable", False) is True


def test_invalid_credential_bundle_fails_before_network() -> None:
    http = FakeHTTP()
    provider = MercadoPagoSubscriptionsBillingProvider(http=http)

    with pytest.raises(BillingAuthenticationError):
        provider.test_connection(
            context=_context(),
            credential=SecretValue('{"access_token":"only-token"}'),
        )
    assert http.calls == []


def test_frontend_runtime_registers_saas_adapter_without_activating_account() -> None:
    source = FRONTEND_APP.read_text(encoding="utf-8")
    assert "MercadoPagoSubscriptionsBillingProvider" in source
    assert "BillingProviderAdapterRegistryV1(" in source
    assert "MERCADO_PAGO_SUBSCRIPTIONS" not in source
