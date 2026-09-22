"""Contratos provider-neutral de billing da FM Commercial Platform — KCA-09."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from core.comercial.erros import DadoComercialInvalido
from core.seguranca.segredos import SecretValue


def _required(value: str, field: str, *, max_length: int = 255) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise DadoComercialInvalido(f"billing_{field}_obrigatorio")
    if len(cleaned) > max_length:
        raise DadoComercialInvalido(f"billing_{field}_excede_limite")
    return cleaned


@dataclass(frozen=True, kw_only=True)
class BillingCallContext:
    idempotency_key: str
    correlation_id: str
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "idempotency_key",
            _required(self.idempotency_key, "idempotency_key", max_length=192),
        )
        object.__setattr__(
            self,
            "correlation_id",
            _required(self.correlation_id, "correlation_id", max_length=128),
        )
        if self.timeout_seconds <= 0 or self.timeout_seconds > 120:
            raise DadoComercialInvalido("billing_timeout_invalido")


@dataclass(frozen=True, kw_only=True)
class BillingCustomerRequest:
    fm_customer_id: str
    product_account_id: str
    contact_email: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fm_customer_id", _required(self.fm_customer_id, "fm_customer_id")
        )
        object.__setattr__(
            self,
            "product_account_id",
            _required(self.product_account_id, "product_account_id"),
        )
        object.__setattr__(
            self, "contact_email", _required(self.contact_email, "contact_email", max_length=320)
        )


@dataclass(frozen=True, kw_only=True)
class BillingCustomerReference:
    provider_code: str
    external_customer_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "provider_code", _required(self.provider_code, "provider_code", max_length=64)
        )
        object.__setattr__(
            self,
            "external_customer_ref",
            _required(self.external_customer_ref, "external_customer_ref"),
        )


@dataclass(frozen=True, kw_only=True)
class CheckoutRequest:
    fm_customer_id: str
    product_account_id: str
    price_id: str
    success_url: str
    cancel_url: str

    def __post_init__(self) -> None:
        for field in ("fm_customer_id", "product_account_id", "price_id"):
            object.__setattr__(self, field, _required(getattr(self, field), field))
        object.__setattr__(
            self, "success_url", _required(self.success_url, "success_url", max_length=2048)
        )
        object.__setattr__(
            self, "cancel_url", _required(self.cancel_url, "cancel_url", max_length=2048)
        )


@dataclass(frozen=True, kw_only=True)
class CheckoutResult:
    provider_code: str
    external_checkout_ref: str
    checkout_url: str


@dataclass(frozen=True, kw_only=True)
class BillingSubscriptionRequest:
    fm_customer_id: str
    product_account_id: str
    external_customer_ref: str
    price_id: str

    def __post_init__(self) -> None:
        for field in (
            "fm_customer_id",
            "product_account_id",
            "external_customer_ref",
            "price_id",
        ):
            object.__setattr__(self, field, _required(getattr(self, field), field))


@dataclass(frozen=True, kw_only=True)
class BillingSubscriptionChangeRequest:
    external_subscription_ref: str
    price_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "external_subscription_ref",
            _required(self.external_subscription_ref, "external_subscription_ref"),
        )
        object.__setattr__(self, "price_id", _required(self.price_id, "price_id"))


@dataclass(frozen=True, kw_only=True)
class ProviderSubscriptionReference:
    provider_code: str
    external_subscription_ref: str
    external_customer_ref: str


@dataclass(frozen=True, kw_only=True)
class BillingTransaction:
    provider_code: str
    external_transaction_ref: str
    status: str
    amount: Decimal
    currency: str


@dataclass(frozen=True, kw_only=True)
class WebhookVerificationResult:
    valid: bool
    event_id: str | None
    event_type: str | None


class BillingProviderError(RuntimeError):
    retryable = False

    def __init__(self, message: str = "billing_provider_error") -> None:
        super().__init__(message)


class BillingProviderUnavailable(BillingProviderError):
    retryable = True


class BillingTimeout(BillingProviderError):
    retryable = True


class BillingAuthenticationError(BillingProviderError):
    pass


class BillingValidationError(BillingProviderError):
    pass


class BillingRateLimited(BillingProviderError):
    retryable = True


class BillingConflict(BillingProviderError):
    pass


class BillingTransactionNotFound(BillingProviderError):
    pass


class BillingWebhookInvalid(BillingProviderError):
    pass


class BillingProvider(Protocol):
    @property
    def provider_code(self) -> str: ...

    def create_customer(
        self,
        *,
        request: BillingCustomerRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingCustomerReference: ...

    def create_checkout(
        self,
        *,
        request: CheckoutRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> CheckoutResult: ...

    def create_subscription(
        self,
        *,
        request: BillingSubscriptionRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference: ...

    def cancel_subscription(
        self,
        *,
        external_subscription_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference: ...

    def change_subscription(
        self,
        *,
        request: BillingSubscriptionChangeRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference: ...

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingTransaction: ...

    def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> WebhookVerificationResult: ...
