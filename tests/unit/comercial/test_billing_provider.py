from __future__ import annotations

from decimal import Decimal

import pytest

from application.commercial_billing import BillingGatewayV1, BillingProviderBinding
from core.comercial.billing import (
    BillingAuthenticationError,
    BillingCallContext,
    BillingConnectionTestResult,
    BillingConflict,
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
from core.comercial.erros import DadoComercialInvalido
from core.seguranca.segredos import ReferenceSecretStore, SecretValue


class FakeBillingProvider:
    provider_code = "FAKE_TEST"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float, str]] = []

    def _capture(
        self,
        operation: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> None:
        self.calls.append(
            (
                operation,
                context.idempotency_key,
                context.timeout_seconds,
                str(credential),
            )
        )
        assert credential.reveal() == "definitely-not-a-real-secret"

    def test_connection(
        self,
        *,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingConnectionTestResult:
        self._capture("test_connection", context, credential)
        return BillingConnectionTestResult(
            ok=True,
            provider_code=self.provider_code,
            detail_code="connection_ok",
        )

    def create_customer(
        self,
        *,
        request: BillingCustomerRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingCustomerReference:
        self._capture("create_customer", context, credential)
        return BillingCustomerReference(
            provider_code=self.provider_code,
            external_customer_ref=f"customer:{request.fm_customer_id}",
        )

    def create_checkout(
        self,
        *,
        request: CheckoutRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> CheckoutResult:
        self._capture("create_checkout", context, credential)
        return CheckoutResult(
            provider_code=self.provider_code,
            external_checkout_ref=f"checkout:{request.product_account_id}",
            checkout_url="https://example.invalid/checkout/test",
        )

    def create_subscription(
        self,
        *,
        request: BillingSubscriptionRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._capture("create_subscription", context, credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=f"subscription:{request.product_account_id}",
            external_customer_ref=request.external_customer_ref,
        )

    def cancel_subscription(
        self,
        *,
        external_subscription_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._capture("cancel_subscription", context, credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=external_subscription_ref,
            external_customer_ref="customer:test",
        )

    def change_subscription(
        self,
        *,
        request: BillingSubscriptionChangeRequest,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> ProviderSubscriptionReference:
        self._capture("change_subscription", context, credential)
        return ProviderSubscriptionReference(
            provider_code=self.provider_code,
            external_subscription_ref=request.external_subscription_ref,
            external_customer_ref="customer:test",
        )

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> BillingTransaction:
        self._capture("fetch_transaction", context, credential)
        return BillingTransaction(
            provider_code=self.provider_code,
            external_transaction_ref=external_transaction_ref,
            status="paid",
            amount=Decimal("99.90"),
            currency="BRL",
        )

    def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
        context: BillingCallContext,
        credential: SecretValue,
    ) -> WebhookVerificationResult:
        self._capture("verify_webhook", context, credential)
        return WebhookVerificationResult(
            valid=payload == b"{}" and signature == "fake-signature",
            event_id="event:test",
            event_type="billing.test",
        )


def _gateway() -> tuple[BillingGatewayV1, FakeBillingProvider]:
    provider = FakeBillingProvider()
    gateway = BillingGatewayV1(
        provider=provider,
        binding=BillingProviderBinding(
            provider_code="FAKE_TEST",
            credential_secret_reference="mapping:billing_test_secret",
        ),
        secret_store=ReferenceSecretStore(
            mapping={"billing_test_secret": "definitely-not-a-real-secret"}
        ),
    )
    return gateway, provider


def _context(key: str) -> BillingCallContext:
    return BillingCallContext(
        idempotency_key=key,
        correlation_id=f"corr-{key}",
        timeout_seconds=7.5,
    )


def test_provider_contract_covers_all_kca09_operations_and_preserves_context() -> None:
    gateway, provider = _gateway()
    customer = gateway.create_customer(
        request=BillingCustomerRequest(
            fm_customer_id="customer-1",
            product_account_id="account-1",
            contact_email="test@example.invalid",
        ),
        context=_context("customer"),
    )
    checkout = gateway.create_checkout(
        request=CheckoutRequest(
            fm_customer_id="customer-1",
            product_account_id="account-1",
            price_id="price-1",
            success_url="https://example.invalid/success",
            cancel_url="https://example.invalid/cancel",
        ),
        context=_context("checkout"),
    )
    subscription = gateway.create_subscription(
        request=BillingSubscriptionRequest(
            fm_customer_id="customer-1",
            product_account_id="account-1",
            external_customer_ref=customer.external_customer_ref,
            price_id="price-1",
        ),
        context=_context("subscription"),
    )
    changed = gateway.change_subscription(
        request=BillingSubscriptionChangeRequest(
            external_subscription_ref=subscription.external_subscription_ref,
            price_id="price-2",
        ),
        context=_context("change"),
    )
    canceled = gateway.cancel_subscription(
        external_subscription_ref=changed.external_subscription_ref,
        context=_context("cancel"),
    )
    transaction = gateway.fetch_transaction(
        external_transaction_ref="transaction-1",
        context=_context("fetch"),
    )
    webhook = gateway.verify_webhook(
        payload=b"{}",
        signature="fake-signature",
        context=_context("webhook"),
    )

    assert customer.provider_code == "FAKE_TEST"
    assert checkout.provider_code == "FAKE_TEST"
    assert canceled.external_subscription_ref == subscription.external_subscription_ref
    assert transaction.currency == "BRL"
    assert webhook.valid is True
    assert [call[0] for call in provider.calls] == [
        "create_customer",
        "create_checkout",
        "create_subscription",
        "change_subscription",
        "cancel_subscription",
        "fetch_transaction",
        "verify_webhook",
    ]
    assert all(call[2] == 7.5 for call in provider.calls)
    assert all(call[3] == "***" for call in provider.calls)


def test_retryability_is_canonical_and_has_no_hidden_retry_loop() -> None:
    assert BillingProviderUnavailable.retryable is True
    assert BillingTimeout.retryable is True
    assert BillingRateLimited.retryable is True

    for error_type in (
        BillingAuthenticationError,
        BillingValidationError,
        BillingConflict,
        BillingTransactionNotFound,
        BillingWebhookInvalid,
    ):
        assert error_type.retryable is False


def test_binding_requires_reference_and_exact_provider_code() -> None:
    provider = FakeBillingProvider()
    with pytest.raises(DadoComercialInvalido, match="billing_secret_reference_invalida"):
        BillingProviderBinding(
            provider_code="FAKE_TEST",
            credential_secret_reference="raw-secret-is-forbidden",
        )

    with pytest.raises(DadoComercialInvalido, match="billing_provider_binding_mismatch"):
        BillingGatewayV1(
            provider=provider,
            binding=BillingProviderBinding(
                provider_code="OTHER",
                credential_secret_reference="mapping:billing_test_secret",
            ),
            secret_store=ReferenceSecretStore(
                mapping={"billing_test_secret": "definitely-not-a-real-secret"}
            ),
        )


def test_call_context_rejects_invalid_timeout_and_idempotency() -> None:
    with pytest.raises(DadoComercialInvalido, match="billing_timeout_invalido"):
        BillingCallContext(
            idempotency_key="key",
            correlation_id="corr",
            timeout_seconds=0,
        )
    with pytest.raises(DadoComercialInvalido, match="billing_idempotency_key_obrigatorio"):
        BillingCallContext(
            idempotency_key=" ",
            correlation_id="corr",
        )
