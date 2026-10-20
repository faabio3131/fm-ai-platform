"""Domínio do Subscription Engine KCA-08."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida


class EstadoAssinatura(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


_TRANSICOES: dict[EstadoAssinatura, frozenset[EstadoAssinatura]] = {
    EstadoAssinatura.PENDING: frozenset(
        {EstadoAssinatura.ACTIVE, EstadoAssinatura.CANCELED}
    ),
    EstadoAssinatura.ACTIVE: frozenset(
        {
            EstadoAssinatura.PAST_DUE,
            EstadoAssinatura.SUSPENDED,
            EstadoAssinatura.CANCELED,
        }
    ),
    EstadoAssinatura.PAST_DUE: frozenset(
        {
            EstadoAssinatura.ACTIVE,
            EstadoAssinatura.SUSPENDED,
            EstadoAssinatura.CANCELED,
        }
    ),
    EstadoAssinatura.SUSPENDED: frozenset(
        {EstadoAssinatura.ACTIVE, EstadoAssinatura.CANCELED}
    ),
    EstadoAssinatura.CANCELED: frozenset(),
}


@dataclass(frozen=True, kw_only=True)
class AssinaturaComercial:
    subscription_id: str
    fm_customer_id: str
    product_account_id: str
    tenant_id: str
    plan_code: str
    plan_version_id: str
    price_id: str
    currency: str
    billing_period: str
    contracted_amount: Decimal
    status: EstadoAssinatura
    current_period_start: datetime | None
    current_period_end: datetime | None
    cancel_at_period_end: bool
    canceled_at: datetime | None
    activated_at: datetime | None
    suspended_at: datetime | None
    version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DadoComercialInvalido("datetime_sem_timezone")
    return value.astimezone(timezone.utc)


def validar_periodo(
    inicio: datetime,
    fim: datetime,
) -> tuple[datetime, datetime]:
    start = utc(inicio)
    end = utc(fim)
    if end <= start:
        raise DadoComercialInvalido("subscription_periodo_invalido")
    return start, end


def validar_transicao_assinatura(
    atual: EstadoAssinatura,
    destino: EstadoAssinatura,
) -> None:
    if destino == atual:
        raise TransicaoComercialInvalida("subscription_transicao_sem_mudanca")
    if destino not in _TRANSICOES[atual]:
        raise TransicaoComercialInvalida(
            f"subscription_transicao_invalida:{atual.value}->{destino.value}"
        )
