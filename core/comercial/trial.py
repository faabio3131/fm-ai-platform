"""Domínio do Trial Engine KCA-07."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from core.comercial.erros import DadoComercialInvalido, TransicaoComercialInvalida

TRIAL_POLICY_VERSION = "KORDENA_TRIAL_30D_V1"
TRIAL_DURATION_DAYS = 30


class EstadoTrial(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    CONVERTED = "converted"
    EXPIRED = "expired"
    REVOKED = "revoked"


_TRANSICOES: dict[EstadoTrial, frozenset[EstadoTrial]] = {
    EstadoTrial.PENDING: frozenset({EstadoTrial.ACTIVE, EstadoTrial.REVOKED}),
    EstadoTrial.ACTIVE: frozenset(
        {EstadoTrial.CONVERTED, EstadoTrial.EXPIRED, EstadoTrial.REVOKED}
    ),
    EstadoTrial.CONVERTED: frozenset(),
    EstadoTrial.EXPIRED: frozenset(),
    EstadoTrial.REVOKED: frozenset(),
}


@dataclass(frozen=True, kw_only=True)
class PoliticaTrial:
    policy_version: str
    duration_days: int
    active: bool
    effective_from: datetime
    created_at: datetime


@dataclass(frozen=True, kw_only=True)
class TrialComercial:
    trial_id: str
    fm_customer_id: str
    product_account_id: str
    tenant_id: str
    plan_code: str
    plan_version_id: str
    status: EstadoTrial
    policy_version: str
    duration_days: int
    started_at: datetime | None
    ends_at: datetime | None
    converted_at: datetime | None
    revoked_at: datetime | None
    override_reason: str | None
    version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime


def utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise DadoComercialInvalido("datetime_sem_timezone")
    return valor.astimezone(timezone.utc)


def validar_transicao_trial(atual: EstadoTrial, destino: EstadoTrial) -> None:
    if destino == atual:
        raise TransicaoComercialInvalida("trial_transicao_sem_mudanca")
    if destino not in _TRANSICOES[atual]:
        raise TransicaoComercialInvalida(
            f"trial_transicao_invalida:{atual.value}->{destino.value}"
        )


def calcular_fim_trial(*, started_at: datetime, duration_days: int) -> datetime:
    inicio = utc(started_at)
    if duration_days <= 0:
        raise DadoComercialInvalido("trial_duration_days_invalido")
    return inicio + timedelta(days=duration_days)


def trial_esta_expirado(trial: TrialComercial, *, agora: datetime) -> bool:
    if trial.status != EstadoTrial.ACTIVE or trial.ends_at is None:
        return False
    return utc(agora) >= utc(trial.ends_at)
