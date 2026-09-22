"""Modelo de domínio do catálogo comercial KCA-03."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida

KORDENA_PLAN_CODES: tuple[str, ...] = (
    "KORDENA_PLAN_A",
    "KORDENA_PLAN_B",
    "KORDENA_PLAN_C",
    "KORDENA_PLAN_D",
)


class StatusConfiguracaoCatalogo(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    REVOKED = "revoked"


class StatusRegistroCatalogo(StrEnum):
    CONFIGURATION_PENDING = "configuration_pending"
    CONFIGURED = "configured"
    REVOKED = "revoked"


class PoliticaMudancaPreco(StrEnum):
    NEW_CUSTOMERS_ONLY = "new_customers_only"
    AT_NEXT_RENEWAL = "at_next_renewal"
    MIGRATION_SCHEDULED = "migration_scheduled"
    MANUAL_MIGRATION = "manual_migration"


class TipoDescontoPromocao(StrEnum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FIXED_PRICE = "fixed_price"


def _texto(
    valor: str,
    campo: str,
    *,
    max_length: int,
    upper: bool = False,
    lower: bool = False,
) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise DadoComercialInvalido(f"{campo}_obrigatorio")
    resultado = valor.strip()
    if upper:
        resultado = resultado.upper()
    if lower:
        resultado = resultado.casefold()
    if len(resultado) > max_length:
        raise DadoComercialInvalido(f"{campo}_excede_limite")
    return resultado


def texto_opcional(valor: str | None, campo: str, *, max_length: int) -> str | None:
    if valor is None:
        return None
    resultado = valor.strip()
    if not resultado:
        return None
    if len(resultado) > max_length:
        raise DadoComercialInvalido(f"{campo}_excede_limite")
    return resultado


def normalizar_plan_code(valor: str) -> str:
    code = _texto(valor, "plan_code", max_length=64, upper=True)
    if code not in KORDENA_PLAN_CODES:
        raise DadoComercialInvalido("plan_code_nao_canonico")
    return code


def normalizar_currency(valor: str) -> str:
    currency = _texto(valor, "currency", max_length=3, upper=True)
    if len(currency) != 3 or not currency.isalpha():
        raise DadoComercialInvalido("currency_invalida")
    return currency


def normalizar_billing_period(valor: str) -> str:
    period = _texto(valor, "billing_period", max_length=32, upper=True)
    if not all(c.isalnum() or c in {"_", "-"} for c in period):
        raise DadoComercialInvalido("billing_period_invalido")
    return period


def normalizar_capability_key(valor: str) -> str:
    key = _texto(valor, "capability_key", max_length=128, lower=True)
    if not all(c.isalnum() or c in {"_", "-", "."} for c in key):
        raise DadoComercialInvalido("capability_key_invalida")
    return key


def normalizar_reason(valor: str) -> str:
    return _texto(valor, "change_reason", max_length=255)


def decimal_monetario(valor: Decimal | str | float) -> Decimal:
    try:
        result = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise DadoComercialInvalido("valor_monetario_invalido") from exc
    if result < 0:
        raise DadoComercialInvalido("valor_monetario_negativo")
    return result


def decimal_limite(valor: Decimal | str | float | None) -> Decimal | None:
    if valor is None:
        return None
    try:
        result = Decimal(str(valor))
    except (InvalidOperation, ValueError) as exc:
        raise DadoComercialInvalido("limit_value_invalido") from exc
    if result < 0:
        raise DadoComercialInvalido("limit_value_negativo")
    return result


def utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise DadoComercialInvalido("datetime_sem_timezone")
    return valor.astimezone(timezone.utc)


def validar_intervalo(inicio: datetime, fim: datetime | None) -> tuple[datetime, datetime | None]:
    start = utc(inicio)
    end = utc(fim) if fim is not None else None
    if end is not None and end <= start:
        raise DadoComercialInvalido("intervalo_invalido")
    return start, end


def validar_desconto(
    tipo: TipoDescontoPromocao,
    valor: Decimal | str | float,
    currency: str | None,
) -> tuple[Decimal, str | None]:
    amount = decimal_monetario(valor)
    if tipo == TipoDescontoPromocao.PERCENTAGE:
        if amount <= 0 or amount > Decimal("100.00"):
            raise DadoComercialInvalido("percentual_promocao_invalido")
        if currency is not None:
            raise DadoComercialInvalido("currency_nao_permitida_em_percentual")
        return amount, None
    if amount <= 0:
        raise DadoComercialInvalido("valor_promocao_deve_ser_positivo")
    if currency is None:
        raise DadoComercialInvalido("currency_obrigatoria_em_desconto_monetario")
    return amount, normalizar_currency(currency)


def validar_transicao_configuracao(
    atual: StatusConfiguracaoCatalogo,
    destino: StatusConfiguracaoCatalogo,
) -> None:
    permitidas = {
        StatusConfiguracaoCatalogo.DRAFT: {
            StatusConfiguracaoCatalogo.VALIDATED,
            StatusConfiguracaoCatalogo.REVOKED,
        },
        StatusConfiguracaoCatalogo.VALIDATED: {
            StatusConfiguracaoCatalogo.PUBLISHED,
            StatusConfiguracaoCatalogo.REVOKED,
        },
        StatusConfiguracaoCatalogo.PUBLISHED: set(),
        StatusConfiguracaoCatalogo.REVOKED: set(),
    }
    if destino not in permitidas[atual]:
        raise TransicaoComercialInvalida(
            f"transicao_catalogo_invalida:{atual.value}->{destino.value}"
        )


@dataclass(frozen=True, kw_only=True)
class PlanoComercial:
    plan_id: str
    product_code: str
    plan_code: str
    rank: int
    status: StatusRegistroCatalogo
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class EntitlementPlano:
    capability_key: str
    enabled: bool
    limit_value: Decimal | None
    limit_unit: str | None
    config: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class VersaoPlanoComercial:
    plan_version_id: str
    plan_id: str
    version_number: int
    display_name: str
    description: str | None
    trial_eligible: bool
    marketing_badge: str | None
    metadata: dict[str, Any]
    status: StatusConfiguracaoCatalogo
    valid_from: datetime | None
    valid_until: datetime | None
    change_reason: str
    created_at: datetime
    validated_at: datetime | None
    published_at: datetime | None
    entitlements: tuple[EntitlementPlano, ...] = ()


@dataclass(frozen=True, kw_only=True)
class PrecoComercial:
    price_id: str
    plan_version_id: str
    revision: int
    currency: str
    billing_period: str
    amount: Decimal
    change_policy: PoliticaMudancaPreco
    status: StatusConfiguracaoCatalogo
    valid_from: datetime | None
    valid_until: datetime | None
    change_reason: str
    created_at: datetime
    validated_at: datetime | None
    published_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class PromocaoComercial:
    promotion_id: str
    promotion_code: str
    product_code: str
    status: StatusRegistroCatalogo
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class VersaoPromocaoComercial:
    promotion_version_id: str
    promotion_id: str
    version_number: int
    name: str
    discount_type: TipoDescontoPromocao
    discount_value: Decimal
    currency: str | None
    starts_at: datetime
    ends_at: datetime | None
    max_redemptions: int | None
    per_customer_limit: int | None
    rules: dict[str, Any]
    eligible_plan_codes: tuple[str, ...]
    status: StatusConfiguracaoCatalogo
    change_reason: str
    created_at: datetime
    validated_at: datetime | None
    published_at: datetime | None
