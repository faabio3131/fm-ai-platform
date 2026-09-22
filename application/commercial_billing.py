"""Application boundary para BillingProvider provider-neutral — KCA-09."""

from __future__ import annotations

from dataclasses import dataclass

from core.comercial.billing import (
    BillingCallContext,
    BillingCustomerReference,
    BillingCustomerRequest,
    BillingProvider,
    BillingSubscriptionChangeRequest,
    BillingSubscriptionRequest,
    BillingTransaction,
    CheckoutRequest,
    CheckoutResult,
    ProviderSubscriptionReference,
    WebhookVerificationResult,
)
from core.comercial.erros import DadoComercialInvalido
from core.seguranca.segredos import SecretStore


@dataclass(frozen=True, kw_only=True)
class BillingProviderBinding:
    provider_code: str
    credential_secret_reference: str

    def __post_init__(self) -> None:
        code = self.provider_code.strip()
        reference = self.credential_secret_reference.strip()
        if not code or len(code) > 64:
            raise DadoComercialInvalido("billing_provider_code_invalido")
        if ":" not in reference or len(reference) > 255:
            raise DadoComercialInvalido("billing_secret_reference_invalida")
        object.__setattr__(self, "provider_code", code)
        object.__setattr__(self, "credential_secret_reference", reference)


class BillingGatewayV1:
    """Boundary fino: resolve secret por referência e delega uma única chamada.

    Retry é responsabilidade de uma policy/orquestração externa. Este gateway não
    executa loops automáticos, evitando duplicação silenciosa de operações financeiras.
    """

    def __init__(
        self,
        *,
        provider: BillingProvider,
        binding: BillingProviderBinding,
        secret_store: SecretStore,
    ) -> None:
        if provider.provider_code != binding.provider_code:
            raise DadoComercialInvalido("billing_provider_binding_mismatch")
        self._provider = provider
        self._binding = binding
        self._secret_store = secret_store

    @property
    def provider_code(self) -> str:
        return self._binding.provider_code

    def _credential(self):
        return self._secret_store.resolve(self._binding.credential_secret_reference)

    def create_customer(
        self,
        *,
        request: BillingCustomerRequest,
        context: BillingCallContext,
    ) -> BillingCustomerReference:
        return self._provider.create_customer(
            request=request,
            context=context,
            credential=self._credential(),
        )

    def create_checkout(
        self,
        *,
        request: CheckoutRequest,
        context: BillingCallContext,
    ) -> CheckoutResult:
        return self._provider.create_checkout(
            request=request,
            context=context,
            credential=self._credential(),
        )

    def create_subscription(
        self,
        *,
        request: BillingSubscriptionRequest,
        context: BillingCallContext,
    ) -> ProviderSubscriptionReference:
        return self._provider.create_subscription(
            request=request,
            context=context,
            credential=self._credential(),
        )

    def cancel_subscription(
        self,
        *,
        external_subscription_ref: str,
        context: BillingCallContext,
    ) -> ProviderSubscriptionReference:
        return self._provider.cancel_subscription(
            external_subscription_ref=external_subscription_ref.strip(),
            context=context,
            credential=self._credential(),
        )

    def change_subscription(
        self,
        *,
        request: BillingSubscriptionChangeRequest,
        context: BillingCallContext,
    ) -> ProviderSubscriptionReference:
        return self._provider.change_subscription(
            request=request,
            context=context,
            credential=self._credential(),
        )

    def fetch_transaction(
        self,
        *,
        external_transaction_ref: str,
        context: BillingCallContext,
    ) -> BillingTransaction:
        return self._provider.fetch_transaction(
            external_transaction_ref=external_transaction_ref.strip(),
            context=context,
            credential=self._credential(),
        )

    def verify_webhook(
        self,
        *,
        payload: bytes,
        signature: str,
        context: BillingCallContext,
    ) -> WebhookVerificationResult:
        return self._provider.verify_webhook(
            payload=payload,
            signature=signature,
            context=context,
            credential=self._credential(),
        )
