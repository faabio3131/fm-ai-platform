"""Adapter SaaS recorrente do Mercado Pago para a FM Commercial Platform.

Este adapter é deliberadamente separado do Mercado Pago operacional usado pelos
estabelecimentos. Ele implementa somente o contrato provider-neutral de billing
da Nova FM/Kordena e não ativa nenhuma conta por si só.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from core.comercial.billing import (
    BillingAuthenticationError,
    BillingCallContext,
    BillingConflict,
    BillingConnectionTestResult,
    BillingCustomerReference,
    BillingCustomerRequest,
    BillingProviderUnavailable,
    BillingRateLimited,
    BillingSubscriptionChangeRequest,
    BillingSubscriptionRequest,
    BillingTimeout,
    BillingTransaction,
    BillingTransactionNotFound,
    BillingValidationError,
    BillingWebhookInvalid,
    CheckoutRequest,
    CheckoutResult,
    ProviderSubscriptionReference,
    WebhookVerificationResult,
)
from core.comercial.billing_events import (
    BillingCanonicalEventType,
    BillingTransactionStatus,
    BillingTransactionType,
    NormalizedBillingEvent,
)
from core.seguranca.segredos import SecretValue

_PROVIDER_CODE = "MERCADO_PAGO_SUBSCRIPTIONS"
_API_BASE = "https://api.mercadopago.com"
_IDENTITY_URL = "https://api.mercadolibre.com/users/me"


class MercadoPagoHTTPResponse(Protocol):
    status_code: int

    def json(self) -> Any: ...


class MercadoPagoHTTPTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, object] | None,
        timeout: float,
    ) -> MercadoPagoHTTPResponse: ...


class _HttpxTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        json: Mapping[str, object] | None,
        timeout: float,
    ) -> MercadoPagoHTTPResponse:
        return httpx.request(
            method,
            url,
            headers=dict(headers),
            json=dict(json) if json is not None else None,
            timeout=timeout,
        )


@dataclass(frozen=True, repr=False, kw_only=True)
class MercadoPagoSubscriptionsCredential:
    access_token: str
    webhook_secret: str

    def __post_init__(self) -> None:
        if not self.access_token.strip() or not self.webhook_secret.strip():
            raise BillingAuthenticationError("billing_credential_incomplete")

    def __repr__(self) -> str:
        return (
            "MercadoPagoSubscriptionsCredential("
            "access_token=***, webhook_secret=***)"
        )


def _credential(secret: SecretValue) -> MercadoPagoSubscriptionsCredential:
    try:
        raw = json.loads(secret.reveal())
    except (json.JSONDecodeError, TypeError) as exc:
        raise BillingAuthenticationError(
            "billing_credential_payload_invalid"
        ) from exc
    if not isinstance(raw, dict):
        raise BillingAuthenticationError("billing_credential_payload_invalid")
    access_token = str(raw.get("access_token") or "").strip()
    webhook_secret = str(raw.get("webhook_secret") or "").strip()
    return MercadoPagoSubscriptionsCredential(
        access_token=access_token,
        webhook_secret=webhook_secret,
    )


def _required_text(
    value: object,
    *,
    code: str,
    max_length: int = 255,
) -> str:
    result = str(value or "").strip()
    if not result or len(result) > max_length:
        raise BillingValidationError(code)
    return result


def _money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BillingValidationError("billing_provider_amount_invalid") from exc
    if amount <= 0:
        raise BillingValidationError("billing_provider_amount_invalid")
    return amount


def _currency(value: object) -> str:
    result = str(value or "").strip().upper()
    if len(result) != 3 or not result.isalpha():
        raise BillingValidationError("billing_provider_currency_invalid")
    return result


def _recurrence(period: str | None) -> tuple[int, str]:
    normalized = str(period or "").strip().upper().replace("-", "_")
    mapping: dict[str, tuple[int, str]] = {
        "DAILY": (1, "days"),
        "DIARIO": (1, "days"),
        "DIÁRIO": (1, "days"),
        "P1D": (1, "days"),
        "WEEKLY": (7, "days"),
        "SEMANAL": (7, "days"),
        "P1W": (7, "days"),
        "MONTHLY": (1, "months"),
        "MENSAL": (1, "months"),
        "P1M": (1, "months"),
        "QUARTERLY": (3, "months"),
        "TRIMESTRAL": (3, "months"),
        "P3M": (3, "months"),
        "SEMIANNUAL": (6, "months"),
        "SEMESTRAL": (6, "months"),
        "P6M": (6, "months"),
        "ANNUAL": (12, "months"),
        "YEARLY": (12, "months"),
        "ANUAL": (12, "months"),
        "P1Y": (12, "months"),
    }
    result = mapping.get(normalized)
    if result is None:
        raise BillingValidationError("billing_period_not_supported_by_provider")
    return result


def _parse_json(response: MercadoPagoHTTPResponse) -> Mapping[str, Any]:
    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise BillingProviderUnavailable(
            "billing_provider_payload_invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise BillingProviderUnavailable("billing_provider_payload_invalid")
    return payload


def _event_time(payload: Mapping[str, Any]) -> datetime:
    for field in ("last_modified", "date_created", "date"):
        raw = payload.get(field)
        if not raw:
            continue
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _idempotency(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise BillingValidationError("billing_idempotency_key_invalid")
    if len(cleaned) <= 128:
        return cleaned
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


class MercadoPagoSubscriptionsBillingProvider:
    """Mercado Pago Subscriptions API behind the canonical billing contract."""

    provider_code = _PROVIDER_CODE
    credential_schema = (
        {
            "key": "access_token",
            "label": "Access Token",
            "secret": True,
        },
        {
            "key": "webhook_secret",
            "label": "Webhook Secret",
            "secret": True,
        },
    )

    def __init__(
        self,
        *,
        http: MercadoPagoHTTPTransport | None = None,
        api_base: str = _API_BASE,
        identity_url: str = _IDENTITY_URL,
    ) -> None:
        self._http = http or _HttpxTransport()
        self._api_base = api_base.rstrip("/")
        self._identity_url = identity_url

    @staticmethod
    def _headers(
        *,
        credentials: MercadoPagoSubscriptionsCredential,
        idempotency_key: str | None = None,
    ) -> dict[str, str]:
        result = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            result["X-Idempotency-Key"] = _idempotency(idempotency_key)
        return result

    def _request(
        self,
        *,
        method: str,
        url: str,
        context: BillingCallContext,
        credentials: MercadoPagoSubscriptionsCredential,
        json_body: Mapping[str, object] | None = None,
        mutation: bool = False,
        not_found_as_transaction: bool = False,
    ) -> Mapping[str, Any]:
        try:
            response = self._http.request(
                method,
                url,
                headers=self._headers(
                    credentials=credentials,
                    idempotency_key=context.idempotency_key if mutation else None,
                ),
                json=json_body,
                timeout=context.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise BillingTimeout("billing_provider_timeout") from exc
        except httpx.RequestError as exc:
            raise BillingProviderUnavailable(
                "billing_provider_transport_unavailable"
            ) from exc

        status_code = int(response.status_code)
        if status_code in {401, 403}:
            raise BillingAuthenticationError("billing_provider_authentication_failed")
        if status_code == 404:
            if not_found_as_transaction:
                raise BillingTransactionNotFound(
                    "billing_provider_transaction_not_found"
                )
            raise BillingValidationError("billing_provider_resource_not_found")
        if status_code == 409:
            raise BillingConflict("billing_provider_conflict")
        if status_code == 429:
            raise BillingRateLimited("billing_provider_rate_limited")
        if status_code in {400, 422}:
            raise BillingValidationError("billing_provider_request_rejected")
        if status_code >= 500:
            raise BillingProviderUnavailable("billing_provider_unavailable")
        if status_code < 200 or status_code >= 300:
            raise BillingProviderUnavailable(
                f"billing_provider_http_{status_code}"
            )
        return _parse_json(response)

    @staticmethod
    def _checkout_fields(
        *,
        contact_email: str | None,
        amount: Decimal | None,
        currency: str | None,
        billing_period: str | None,
        description: str | None,
    ) -> tuple[str, Decimal, str, tuple[int, str], str]:
        email = _required_text(
            contact_email,
            code="billing_contact_email_required",
            max_length=320,
        )
        if "@" not in email:
            raise BillingValidationError("billing_contact_email_invalid")
        recurring_amount = _money(amount)
        recurring_currency = _currency(currency)
        recurrence = _recurrence(billing_period)
        reason = _required_text(
            description or "Kordena",
            code="billing_description_required",
            max_length=255,
        )
        return email, recurring_amount, recurring_currency, recurrence, reason

    def test_connection(
        self,
        *,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingConnectionTestResult:
        credentials = _credential(credential)
        payload = self._request(
            method="GET",
            url=self._identity_url,
            context=context,
            credentials=credentials,
        )
        ok = bool(str(payload.get("id") or "").strip())
        return BillingConnectionTestResult(
            ok=ok,
            provider_code=self.provider_code,
            detail_code="connection_ok" if ok else "connection_identity_missing",
        )

    def create_customer(
        self,
        *,
        request: BillingCustomerRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingCustomerReference:
        credentials = _credential(credential)
        payload = self._request(
            method="POST",
            url=f"{self._api_base}/v1/customers",
            context=context,
            credentials=credentials,
            mutation=True,
            json_body={"email": request.contact_email},
        )
        customer_ref = _required_text(
            payload.get("id"),
            code="billing_provider_customer_ref_missing",
        )
        return BillingCustomerReference(
            provider_code=self.provider_code,
            external_customer_ref=customer_ref,
        )

    def _create_preapproval(
        self,
        *,
        fm_customer_id: str,
        product_account_id: str,
        subscription_id: str | None,
        contact_email: str | None,
        amount: Decimal | None,
        currency: str | None,
        billing_period: str | None,
        description: str | None,
        back_url: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> tuple[Mapping[str, Any], str]:
        credentials = _credential(credential)
        email, recurring_amount, recurring_currency, recurrence, reason = (
            self._checkout_fields(
                contact_email=contact_email,
                amount=amount,
                currency=currency,
                billing_period=billing_period,
                description=description,
            )
        )
        frequency, frequency_type = recurrence
        external_reference = (
            subscription_id.strip()
            if subscription_id and subscription_id.strip()
            else product_account_id.strip()
        )
        if not external_reference:
            external_reference = fm_customer_id.strip()
        body: dict[str, object] = {
            "reason": reason,
            "external_reference": external_reference,
            "payer_email": email,
            "auto_recurring": {
                "frequency": frequency,
                "frequency_type": frequency_type,
                "transaction_amount": float(recurring_amount),
                "currency_id": recurring_currency,
            },
            "back_url": _required_text(
                back_url,
                code="billing_back_url_required",
                max_length=2048,
            ),
            "status": "pending",
        }
        payload = self._request(
            method="POST",
            url=f"{self._api_base}/preapproval",
            context=context,
            credentials=credentials,
            mutation=True,
            json_body=body,
        )
        return payload, email

    def create_checkout(
        self,
        *,
        request: CheckoutRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> CheckoutResult:
        payload, _ = self._create_preapproval(
            fm_customer_id=request.fm_customer_id,
            product_account_id=request.product_account_id,
            subscription_id=request.subscription_id,
            contact_email=request.contact_email,
            amount=request.amount,
            currency=request.currency,
            billing_period=request.billing_period,
            description=request.description,
            back_url=request.success_url,
            context=context,
            credential=credential,
        )
        subscription_ref = _required_text(
            payload.get("id"),
            code="billing_provider_subscription_ref_missing",
        )
        checkout_url = _required_text(
            payload.get("init_point"),
            code="billing_provider_checkout_url_missing",
            max_length=2048,
        )
        return CheckoutResult(
            provider_code=self.provider_code,
            external_checkout_ref=subscription_ref,
            checkout_url=checkout_url,
            external_subscription_ref=subscription_ref,
            external_customer_ref=None,
        )

    def create_subscription(
        self,
        *,
        request: BillingSubscriptionRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        payload, _ = self._create_preapproval(
            fm_customer_id=request.fm_customer_id,
            product_account_id=request.product_account_id,
            subscription_id=None,
            contact_email=request.contact_email,
            amount=request.amount,
            currency=request.currency,
            billing_period=request.billing_period,
            description=request.description,
            back_url="https://kordenaia.com.br",
            context=context,
            credential=credential,
        )
        subscription_ref = _required_text(
            payload.get("id"),
            code="billing_provider_subscription_ref_missing",
        )
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=subscription_ref,
            external_customer_ref=request.external_customer_ref,
        )

    def cancel_subscription(
        self,
        *,
        external_subscription_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        credentials = _credential(credential)
        subscription_ref = _required_text(
            external_subscription_ref,
            code="billing_provider_subscription_ref_required",
        )
        payload = self._request(
            method="PUT",
            url=f"{self._api_base}/preapproval/{subscription_ref}",
            context=context,
            credentials=credentials,
            mutation=True,
            json_body={"status": "canceled"},
        )
        result_ref = _required_text(
            payload.get("id") or subscription_ref,
            code="billing_provider_subscription_ref_missing",
        )
        payer = payload.get("payer_id") or payload.get("payer_email") or "unavailable"
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=result_ref,
            external_customer_ref=str(payer),
        )

    def change_subscription(
        self,
        *,
        request: BillingSubscriptionChangeRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        credentials = _credential(credential)
        amount = _money(request.amount)
        currency = _currency(request.currency)
        auto_recurring: dict[str, object] = {
            "transaction_amount": float(amount),
            "currency_id": currency,
        }
        if request.billing_period:
            frequency, frequency_type = _recurrence(request.billing_period)
            auto_recurring.update(
                {
                    "frequency": frequency,
                    "frequency_type": frequency_type,
                }
            )
        payload = self._request(
            method="PUT",
            url=(
                f"{self._api_base}/preapproval/"
                f"{request.external_subscription_ref}"
            ),
            context=context,
            credentials=credentials,
            mutation=True,
            json_body={"auto_recurring": auto_recurring},
        )
        result_ref = _required_text(
            payload.get("id") or request.external_subscription_ref,
            code="billing_provider_subscription_ref_missing",
        )
        payer = payload.get("payer_id") or payload.get("payer_email") or "unavailable"
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=result_ref,
            external_customer_ref=str(payer),
        )

    @staticmethod
    def _invoice_status(payload: Mapping[str, Any]) -> str:
        payment = payload.get("payment")
        payment_status = ""
        if isinstance(payment, Mapping):
            payment_status = str(payment.get("status") or "").strip().casefold()
        summarized = str(payload.get("summarized") or "").strip().casefold()
        status = str(payload.get("status") or "").strip().casefold()
        candidate = payment_status or summarized or status
        if candidate in {"approved", "accredited", "paid", "succeeded", "charged"}:
            return BillingTransactionStatus.SUCCEEDED.value
        if candidate in {"refunded", "reimbursed"}:
            return BillingTransactionStatus.REFUNDED.value
        if candidate in {
            "rejected",
            "cancelled",
            "canceled",
            "failed",
            "failure",
        }:
            return BillingTransactionStatus.FAILED.value
        return BillingTransactionStatus.PENDING.value

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingTransaction:
        credentials = _credential(credential)
        transaction_ref = _required_text(
            external_transaction_ref,
            code="billing_provider_transaction_ref_required",
        )
        payload = self._request(
            method="GET",
            url=f"{self._api_base}/authorized_payments/{transaction_ref}",
            context=context,
            credentials=credentials,
            not_found_as_transaction=True,
        )
        result_ref = _required_text(
            payload.get("id") or transaction_ref,
            code="billing_provider_transaction_ref_missing",
        )
        return BillingTransaction(
            provider_code=self.provider_code,
            external_transaction_ref=result_ref,
            status=self._invoice_status(payload),
            amount=_money(payload.get("transaction_amount")),
            currency=_currency(payload.get("currency_id")),
        )

    @staticmethod
    def _webhook_payload(payload: bytes) -> Mapping[str, Any]:
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BillingWebhookInvalid("billing_webhook_payload_invalid") from exc
        if not isinstance(decoded, Mapping):
            raise BillingWebhookInvalid("billing_webhook_payload_invalid")
        return decoded

    @staticmethod
    def _signature_parts(value: str) -> tuple[str, str]:
        parts = {
            key.strip(): item.strip()
            for raw in value.split(",")
            if "=" in raw
            for key, item in (raw.split("=", 1),)
        }
        return parts.get("ts", ""), parts.get("v1", "").casefold()

    def verify_webhook(
        self,
        *,
        payload: bytes,
        headers: Mapping[str, str],
        context: BillingCallContext,
        credential: SecretValue,
    ) -> WebhookVerificationResult:
        del context
        credentials = _credential(credential)
        data = self._webhook_payload(payload)
        resource = data.get("data")
        data_id = (
            str(resource.get("id") or "").strip()
            if isinstance(resource, Mapping)
            else ""
        )
        request_id = str(
            headers.get("x-request-id")
            or headers.get("X-Request-Id")
            or ""
        ).strip()
        signature = str(
            headers.get("x-signature")
            or headers.get("X-Signature")
            or ""
        ).strip()
        ts, received = self._signature_parts(signature)
        if not data_id or not request_id or not ts or not received:
            return WebhookVerificationResult(
                valid=False,
                event_id=None,
                event_type=None,
            )
        manifest = f"id:{data_id};request-id:{request_id};ts:{ts};"
        expected = hmac.new(
            credentials.webhook_secret.encode("utf-8"),
            manifest.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        event_id = str(data.get("id") or request_id).strip() or request_id
        event_type = str(data.get("type") or data.get("action") or "").strip()
        return WebhookVerificationResult(
            valid=hmac.compare_digest(expected, received),
            event_id=event_id,
            event_type=event_type or None,
        )

    def _fetch_subscription(
        self,
        *,
        subscription_ref: str,
        context: BillingCallContext,
        credentials: MercadoPagoSubscriptionsCredential,
    ) -> Mapping[str, Any]:
        return self._request(
            method="GET",
            url=f"{self._api_base}/preapproval/{subscription_ref}",
            context=context,
            credentials=credentials,
        )

    def _normalize_subscription_event(
        self,
        *,
        payload: Mapping[str, Any],
        subscription_ref: str,
        verification: WebhookVerificationResult,
    ) -> NormalizedBillingEvent:
        status = str(payload.get("status") or "").strip().casefold()
        mapping = {
            "authorized": BillingCanonicalEventType.SUBSCRIPTION_ACTIVE,
            "paused": BillingCanonicalEventType.SUBSCRIPTION_SUSPENDED,
            "canceled": BillingCanonicalEventType.SUBSCRIPTION_CANCELED,
            "cancelled": BillingCanonicalEventType.SUBSCRIPTION_CANCELED,
        }
        event_type = mapping.get(status)
        if event_type is None:
            raise BillingValidationError(
                f"billing_subscription_status_not_canonical:{status or 'missing'}"
            )
        version_raw = payload.get("version")
        try:
            sequence = int(version_raw) if version_raw is not None else None
        except (TypeError, ValueError):
            sequence = None
        return NormalizedBillingEvent(
            provider_code=self.provider_code,
            external_event_id=verification.event_id or subscription_ref,
            canonical_event_type=event_type,
            occurred_at=_event_time(payload),
            provider_sequence=sequence,
            external_subscription_ref=subscription_ref,
            metadata_safe={"provider_status": status},
        )

    def _normalize_invoice_event(
        self,
        *,
        payload: Mapping[str, Any],
        transaction_ref: str,
        verification: WebhookVerificationResult,
    ) -> NormalizedBillingEvent:
        status = self._invoice_status(payload)
        event_map = {
            BillingTransactionStatus.SUCCEEDED.value: (
                BillingCanonicalEventType.PAYMENT_SUCCEEDED,
                BillingTransactionStatus.SUCCEEDED,
            ),
            BillingTransactionStatus.FAILED.value: (
                BillingCanonicalEventType.PAYMENT_FAILED,
                BillingTransactionStatus.FAILED,
            ),
            BillingTransactionStatus.REFUNDED.value: (
                BillingCanonicalEventType.PAYMENT_REFUNDED,
                BillingTransactionStatus.REFUNDED,
            ),
        }
        mapped = event_map.get(status)
        if mapped is None:
            raise BillingValidationError(
                "billing_invoice_status_not_terminal"
            )
        canonical_event, canonical_status = mapped
        subscription_ref = str(payload.get("preapproval_id") or "").strip() or None
        return NormalizedBillingEvent(
            provider_code=self.provider_code,
            external_event_id=verification.event_id or transaction_ref,
            canonical_event_type=canonical_event,
            occurred_at=_event_time(payload),
            external_subscription_ref=subscription_ref,
            external_transaction_ref=transaction_ref,
            transaction_type=BillingTransactionType.PAYMENT,
            transaction_status=canonical_status,
            amount=_money(payload.get("transaction_amount")),
            currency=_currency(payload.get("currency_id")),
            metadata_safe={"provider_status": status},
        )

    def normalize_webhook(
        self,
        *,
        payload: bytes,
        verification: WebhookVerificationResult,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> NormalizedBillingEvent:
        if not verification.valid:
            raise BillingWebhookInvalid("billing_webhook_signature_invalid")
        data = self._webhook_payload(payload)
        resource = data.get("data")
        resource_id = (
            str(resource.get("id") or "").strip()
            if isinstance(resource, Mapping)
            else ""
        )
        if not resource_id:
            raise BillingWebhookInvalid("billing_webhook_resource_missing")
        credentials = _credential(credential)
        event_type = str(
            verification.event_type
            or data.get("type")
            or data.get("action")
            or ""
        ).strip().casefold()

        if event_type in {
            "subscription_preapproval",
            "preapproval",
            "subscription",
        }:
            subscription = self._fetch_subscription(
                subscription_ref=resource_id,
                context=context,
                credentials=credentials,
            )
            return self._normalize_subscription_event(
                payload=subscription,
                subscription_ref=resource_id,
                verification=verification,
            )

        if event_type in {
            "subscription_authorized_payment",
            "authorized_payment",
            "payment",
        }:
            invoice = self._request(
                method="GET",
                url=f"{self._api_base}/authorized_payments/{resource_id}",
                context=context,
                credentials=credentials,
                not_found_as_transaction=True,
            )
            return self._normalize_invoice_event(
                payload=invoice,
                transaction_ref=resource_id,
                verification=verification,
            )

        raise BillingWebhookInvalid("billing_webhook_event_type_unsupported")
