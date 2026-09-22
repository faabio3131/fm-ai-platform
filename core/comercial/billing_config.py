"""Domínio de configuração multi-provider e contas recebedoras — KCA-09B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida


class BillingEnvironment(StrEnum):
    SANDBOX = "sandbox"
    PRODUCTION = "production"


class BillingPaymentMethod(StrEnum):
    PIX = "pix"
    CARD = "card"
    BOLETO = "boleto"
    BANK_TRANSFER = "bank_transfer"


class BillingProviderAccountStatus(StrEnum):
    DRAFT = "draft"
    VALIDATING = "validating"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class BillingConnectionTestStatus(StrEnum):
    NEVER = "never"
    PASS = "pass"
    FAIL = "fail"


_PROVIDER_TRANSITIONS: dict[
    BillingProviderAccountStatus, frozenset[BillingProviderAccountStatus]
] = {
    BillingProviderAccountStatus.DRAFT: frozenset(
        {
            BillingProviderAccountStatus.VALIDATING,
            BillingProviderAccountStatus.DISABLED,
        }
    ),
    BillingProviderAccountStatus.VALIDATING: frozenset(
        {
            BillingProviderAccountStatus.ACTIVE,
            BillingProviderAccountStatus.DISABLED,
        }
    ),
    BillingProviderAccountStatus.ACTIVE: frozenset(
        {
            BillingProviderAccountStatus.VALIDATING,
            BillingProviderAccountStatus.SUSPENDED,
            BillingProviderAccountStatus.DISABLED,
        }
    ),
    BillingProviderAccountStatus.SUSPENDED: frozenset(
        {
            BillingProviderAccountStatus.VALIDATING,
            BillingProviderAccountStatus.DISABLED,
        }
    ),
    BillingProviderAccountStatus.DISABLED: frozenset(),
}


def normalizar_provider_code(value: str) -> str:
    code = value.strip().upper()
    if not code or len(code) > 64:
        raise DadoComercialInvalido("billing_provider_code_invalido")
    if not all(char.isalnum() or char in {"_", "-", "."} for char in code):
        raise DadoComercialInvalido("billing_provider_code_invalido")
    return code


def normalizar_secret_reference(value: str) -> str:
    reference = value.strip()
    if (
        not reference
        or len(reference) > 255
        or ":" not in reference
        or reference.startswith(":")
        or reference.endswith(":")
    ):
        raise DadoComercialInvalido("billing_secret_reference_invalida")
    return reference


def normalizar_payment_methods(
    methods: tuple[BillingPaymentMethod, ...] | list[BillingPaymentMethod],
) -> tuple[BillingPaymentMethod, ...]:
    unique = tuple(dict.fromkeys(methods))
    if not unique:
        raise DadoComercialInvalido("billing_payment_methods_obrigatorios")
    return unique


def validar_transicao_provider_account(
    atual: BillingProviderAccountStatus,
    destino: BillingProviderAccountStatus,
    *,
    last_test_status: BillingConnectionTestStatus,
) -> None:
    if destino == atual:
        raise TransicaoComercialInvalida("billing_provider_status_sem_mudanca")
    if destino not in _PROVIDER_TRANSITIONS[atual]:
        raise TransicaoComercialInvalida(
            f"billing_provider_status_invalido:{atual.value}->{destino.value}"
        )
    if (
        destino == BillingProviderAccountStatus.ACTIVE
        and last_test_status != BillingConnectionTestStatus.PASS
    ):
        raise TransicaoComercialInvalida(
            "billing_provider_activation_requires_connection_test"
        )


@dataclass(frozen=True, kw_only=True)
class BillingProviderAccount:
    provider_account_id: str
    provider_code: str
    display_name: str
    legal_entity_ref: str | None
    environment: BillingEnvironment
    status: BillingProviderAccountStatus
    credential_secret_reference: str
    supported_payment_methods: tuple[BillingPaymentMethod, ...]
    supports_recurring: bool
    supports_webhooks: bool
    priority: int
    last_tested_at: datetime | None
    last_test_status: BillingConnectionTestStatus
    version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class BillingRoutingPolicy:
    routing_policy_id: str
    product_code: str
    payment_method: BillingPaymentMethod
    environment: BillingEnvironment
    primary_provider_account_id: str
    fallback_provider_account_ids: tuple[str, ...]
    active: bool
    version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class BillingRouteAccount:
    provider_account_id: str
    provider_code: str
    priority: int


@dataclass(frozen=True, kw_only=True)
class BillingRouteDecision:
    product_code: str
    payment_method: BillingPaymentMethod
    environment: BillingEnvironment
    accounts: tuple[BillingRouteAccount, ...]

    @property
    def primary(self) -> BillingRouteAccount:
        if not self.accounts:
            raise DadoComercialInvalido("billing_route_unavailable")
        return self.accounts[0]
