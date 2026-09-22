"""Application boundary para BillingProvider provider-neutral — KCA-09."""

from __future__ import annotations

from dataclasses import dataclass

from core.comercial.billing import (
    BillingCallContext,
    BillingConnectionTestResult,
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
from core.comercial.billing_config import normalizar_provider_code
from core.comercial.erros import DadoComercialInvalido
from core.seguranca.segredos import SecretStore


@dataclass(frozen=True, kw_only=True)
class BillingProviderBinding:
    provider_code: str
    credential_secret_reference: str

    def __post_init__(self) -> None:
        code = normalizar_provider_code(self.provider_code)
        reference = self.credential_secret_reference.strip()
        if ":" not in reference or len(reference) > 255:
            raise DadoComercialInvalido("billing_secret_reference_invalida")
        object.__setattr__(self, "provider_code", code)
        object.__setattr__(self, "credential_secret_reference", reference)


class BillingProviderAdapterRegistryV1:
    """Registry runtime de adapters, sem lista fechada de providers."""

    def __init__(self, providers: tuple[BillingProvider, ...] = ()) -> None:
        self._providers: dict[str, BillingProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: BillingProvider) -> None:
        code = normalizar_provider_code(provider.provider_code)
        if code in self._providers:
            raise DadoComercialInvalido("billing_provider_adapter_duplicado")
        self._providers[code] = provider

    def resolve(self, provider_code: str) -> BillingProvider:
        code = normalizar_provider_code(provider_code)
        provider = self._providers.get(code)
        if provider is None:
            raise DadoComercialInvalido("billing_provider_adapter_nao_registrado")
        return provider

    def available_provider_codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


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

    def test_connection(
        self,
        *,
        context: BillingCallContext,
    ) -> BillingConnectionTestResult:
        return self._provider.test_connection(
            context=context,
            credential=self._credential(),
        )

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
