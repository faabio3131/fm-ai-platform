"""Orquestração de checkout recorrente e recovery comercial — KCA-11."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from application.commercial_billing import (
    BillingGatewayV1,
    BillingProviderAdapterRegistryV1,
    BillingProviderBinding,
)
from application.commercial_billing_config import AplicacaoBillingConfigurationV1
from application.commercial_billing_events import AplicacaoBillingEventsV1
from application.commercial_subscription import AplicacaoSubscriptionComercialV1
from core.comercial.billing import BillingCallContext, CheckoutRequest
from core.comercial.billing_config import BillingEnvironment, BillingPaymentMethod
from core.comercial.erros import (
    DadoComercialInvalido,
    RegistroComercialNaoEncontrado,
)
from core.comercial.modelos import StatusContaProduto
from core.comercial.subscription import AssinaturaComercial, EstadoAssinatura
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import ReferenceSecretStore, SecretStore
from infra.comercial.repositorio_sqlalchemy import RepositorioComercialSQLAlchemy
from infra.seguranca.segredos_sqlalchemy import EncryptedSQLAlchemySecretStore

SessionFactory = Callable[[], Session]


@dataclass(frozen=True, kw_only=True)
class ResultadoCheckoutComercial:
    subscription: AssinaturaComercial
    provider_account_id: str
    provider_code: str
    external_checkout_ref: str
    checkout_url: str
    billing_binding_id: str


def _idempotency(prefix: str, value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 192:
        raise DadoComercialInvalido("idempotency_key_invalida")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


class AplicacaoCheckoutComercialV1:
    """Coordena autoridades existentes sem criar billing paralelo."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        adapter_registry: BillingProviderAdapterRegistryV1,
        fallback_secret_store: SecretStore | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._adapter_registry = adapter_registry
        self._fallback_secret_store = fallback_secret_store or ReferenceSecretStore()
        self._billing_config = AplicacaoBillingConfigurationV1(
            session_factory,
            adapter_registry=adapter_registry,
            secret_store=self._fallback_secret_store,
        )
        self._billing_events = AplicacaoBillingEventsV1(
            session_factory,
            adapter_registry=adapter_registry,
            fallback_secret_store=self._fallback_secret_store,
        )
        self._subscriptions = AplicacaoSubscriptionComercialV1(session_factory)

    @staticmethod
    def _validar_escopo(contexto: ContextoExecucao, tenant_id: str) -> str:
        tenant = tenant_id.strip()
        if not tenant or contexto.tenant_id != tenant:
            raise PermissionError("seguranca.tenant_product_account_mismatch")
        return tenant

    def _subscription(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        tenant_id: str,
        plan_code: str,
        plan_version_id: str,
        price_id: str,
    ) -> AssinaturaComercial:
        with self._session_factory() as session:
            account = RepositorioComercialSQLAlchemy(
                session
            ).obter_conta_produto_por_tenant(
                product_code="KORDENA",
                product_tenant_id=tenant_id,
            )
        if account is None:
            raise RegistroComercialNaoEncontrado("product_account_not_found")
        if account.status != StatusContaProduto.ACTIVE:
            raise DadoComercialInvalido("product_account_not_active")

        current = self._subscriptions.obter_por_product_account(
            product_account_id=account.product_account_id
        )
        if current is None:
            return self._subscriptions.criar_pendente(
                contexto=contexto,
                idempotency_key=_idempotency("checkout-subscription", idempotency_key),
                fm_customer_id=account.fm_customer_id,
                product_account_id=account.product_account_id,
                tenant_id=tenant_id,
                plan_code=plan_code,
                plan_version_id=plan_version_id,
                price_id=price_id,
            )

        if current.status == EstadoAssinatura.ACTIVE:
            raise DadoComercialInvalido("subscription_already_active")
        if current.status == EstadoAssinatura.CANCELED:
            raise DadoComercialInvalido(
                "subscription_canceled_requires_commercial_policy"
            )
        if (
            current.plan_code != plan_code.strip().upper()
            or current.plan_version_id != plan_version_id.strip()
            or current.price_id != price_id.strip()
        ):
            raise DadoComercialInvalido("checkout_subscription_binding_mismatch")
        if current.status not in {
            EstadoAssinatura.PENDING,
            EstadoAssinatura.PAST_DUE,
            EstadoAssinatura.SUSPENDED,
        }:
            raise DadoComercialInvalido("subscription_not_checkout_recoverable")
        return current

    def _provider_account(
        self,
        *,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
    ):
        route = self._billing_config.resolver_rota(
            product_code="KORDENA",
            payment_method=payment_method,
            environment=environment,
        )
        for route_account in route.accounts:
            account = self._billing_config.obter_provider_account(
                provider_account_id=route_account.provider_account_id
            )
            if (
                account.supports_recurring
                and account.supports_webhooks
                and account.credential_secret_reference
            ):
                return account
        raise DadoComercialInvalido("billing_recurring_route_unavailable")

    def iniciar(
        self,
        *,
        contexto: ContextoExecucao,
        idempotency_key: str,
        tenant_id: str,
        plan_code: str,
        plan_version_id: str,
        price_id: str,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
        success_url: str,
        cancel_url: str,
    ) -> ResultadoCheckoutComercial:
        tenant = self._validar_escopo(contexto, tenant_id)
        subscription = self._subscription(
            contexto=contexto,
            idempotency_key=idempotency_key,
            tenant_id=tenant,
            plan_code=plan_code,
            plan_version_id=plan_version_id,
            price_id=price_id,
        )
        account = self._provider_account(
            payment_method=payment_method,
            environment=environment,
        )
        secret_ref = account.credential_secret_reference
        if not secret_ref:
            raise DadoComercialInvalido("billing_credential_not_configured")

        provider = self._adapter_registry.resolve(account.provider_code)
        call_context = BillingCallContext(
            idempotency_key=_idempotency("checkout", idempotency_key),
            correlation_id=contexto.correlation_id,
            timeout_seconds=10.0,
        )
        request = CheckoutRequest(
            fm_customer_id=subscription.fm_customer_id,
            product_account_id=subscription.product_account_id,
            price_id=subscription.price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            subscription_id=subscription.subscription_id,
        )

        if secret_ref.startswith("vault:"):
            with self._session_factory() as session:
                gateway = BillingGatewayV1(
                    provider=provider,
                    binding=BillingProviderBinding(
                        provider_code=account.provider_code,
                        credential_secret_reference=secret_ref,
                    ),
                    secret_store=EncryptedSQLAlchemySecretStore(session),
                )
                checkout = gateway.create_checkout(
                    request=request,
                    context=call_context,
                )
        else:
            gateway = BillingGatewayV1(
                provider=provider,
                binding=BillingProviderBinding(
                    provider_code=account.provider_code,
                    credential_secret_reference=secret_ref,
                ),
                secret_store=self._fallback_secret_store,
            )
            checkout = gateway.create_checkout(
                request=request,
                context=call_context,
            )

        if checkout.provider_code.strip().upper() != account.provider_code:
            raise DadoComercialInvalido("billing_checkout_provider_mismatch")
        external_subscription_ref = (
            checkout.external_subscription_ref.strip()
            if checkout.external_subscription_ref
            else ""
        )
        if not external_subscription_ref:
            raise DadoComercialInvalido(
                "billing_checkout_subscription_binding_required"
            )

        binding_id = self._billing_events.registrar_subscription_binding(
            contexto=contexto,
            provider_account_id=account.provider_account_id,
            subscription_id=subscription.subscription_id,
            external_subscription_ref=external_subscription_ref,
            external_customer_ref=checkout.external_customer_ref,
        )
        return ResultadoCheckoutComercial(
            subscription=subscription,
            provider_account_id=account.provider_account_id,
            provider_code=account.provider_code,
            external_checkout_ref=checkout.external_checkout_ref,
            checkout_url=checkout.checkout_url,
            billing_binding_id=binding_id,
        )
