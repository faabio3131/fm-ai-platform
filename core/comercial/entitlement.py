"""Domínio de entitlement comercial KCA-04."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from core.comercial.catalogo import EntitlementPlano, normalizar_capability_key
from core.comercial.erros import DadoComercialInvalido


class EstadoComercial(StrEnum):
    CONFIGURATION_PENDING = "configuration_pending"
    TRIAL_PENDING = "trial_pending"
    TRIAL_ACTIVE = "trial_active"
    TRIAL_EXPIRED = "trial_expired"
    SUBSCRIPTION_ACTIVE = "subscription_active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELED = "canceled"
    INTERNAL_TEST = "internal_test"


class ModoAcessoComercial(StrEnum):
    FULL = "full"
    LIMITED = "limited"
    BILLING_ONLY = "billing_only"
    BLOCKED = "blocked"


class EntitlementNegado(DadoComercialInvalido):
    """Operação recusada pelo gate comercial fail-closed."""


@dataclass(frozen=True, kw_only=True)
class CapabilityEntitlement:
    capability_key: str
    enabled: bool
    limit_value: Decimal | None
    limit_unit: str | None
    config: dict[str, Any]


@dataclass(frozen=True, kw_only=True)
class SnapshotEntitlement:
    entitlement_snapshot_id: str
    product_account_id: str
    tenant_id: str
    revision: int
    commercial_state: EstadoComercial
    plan_code: str | None
    plan_version_id: str | None
    access_mode: ModoAcessoComercial
    capabilities: tuple[CapabilityEntitlement, ...]
    effective_from: datetime
    valid_until: datetime
    generated_at: datetime


@dataclass(frozen=True, kw_only=True)
class DecisaoEntitlement:
    allowed: bool
    access_mode: ModoAcessoComercial
    reason: str
    revision: int | None
    stale: bool
    capability: CapabilityEntitlement | None = None


def utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise DadoComercialInvalido("datetime_sem_timezone")
    return valor.astimezone(timezone.utc)


def normalizar_estado_comercial(valor: EstadoComercial | str) -> EstadoComercial:
    try:
        return valor if isinstance(valor, EstadoComercial) else EstadoComercial(valor)
    except ValueError as exc:
        raise DadoComercialInvalido("commercial_state_invalido") from exc


def modo_para_estado(estado: EstadoComercial) -> ModoAcessoComercial:
    if estado in {
        EstadoComercial.TRIAL_ACTIVE,
        EstadoComercial.SUBSCRIPTION_ACTIVE,
        EstadoComercial.INTERNAL_TEST,
    }:
        return ModoAcessoComercial.FULL
    if estado == EstadoComercial.PAST_DUE:
        return ModoAcessoComercial.LIMITED
    if estado in {
        EstadoComercial.TRIAL_EXPIRED,
        EstadoComercial.SUSPENDED,
        EstadoComercial.CANCELED,
    }:
        return ModoAcessoComercial.BILLING_ONLY
    return ModoAcessoComercial.BLOCKED


def capabilities_do_plano(
    entitlements: tuple[EntitlementPlano, ...],
) -> tuple[CapabilityEntitlement, ...]:
    return tuple(
        CapabilityEntitlement(
            capability_key=item.capability_key,
            enabled=item.enabled,
            limit_value=item.limit_value,
            limit_unit=item.limit_unit,
            config=dict(item.config),
        )
        for item in sorted(entitlements, key=lambda value: value.capability_key)
    )


def capability_por_chave(
    capabilities: tuple[CapabilityEntitlement, ...],
    capability_key: str,
) -> CapabilityEntitlement | None:
    key = normalizar_capability_key(capability_key)
    return next((item for item in capabilities if item.capability_key == key), None)


def serializar_capabilities(
    capabilities: tuple[CapabilityEntitlement, ...],
) -> dict[str, dict[str, object]]:
    return {
        item.capability_key: {
            "enabled": item.enabled,
            "limit_value": str(item.limit_value) if item.limit_value is not None else None,
            "limit_unit": item.limit_unit,
            "config": dict(item.config),
        }
        for item in capabilities
    }


def desserializar_capabilities(
    payload: dict[str, object],
) -> tuple[CapabilityEntitlement, ...]:
    result: list[CapabilityEntitlement] = []
    for raw_key, raw_value in sorted(payload.items()):
        key = normalizar_capability_key(raw_key)
        if not isinstance(raw_value, dict):
            raise DadoComercialInvalido("capability_payload_invalido")
        enabled = raw_value.get("enabled")
        if not isinstance(enabled, bool):
            raise DadoComercialInvalido("capability_enabled_invalido")
        raw_limit = raw_value.get("limit_value")
        limit_value = Decimal(str(raw_limit)) if raw_limit is not None else None
        raw_unit = raw_value.get("limit_unit")
        if raw_unit is not None and not isinstance(raw_unit, str):
            raise DadoComercialInvalido("capability_limit_unit_invalida")
        raw_config = raw_value.get("config", {})
        if not isinstance(raw_config, dict):
            raise DadoComercialInvalido("capability_config_invalida")
        result.append(
            CapabilityEntitlement(
                capability_key=key,
                enabled=enabled,
                limit_value=limit_value,
                limit_unit=raw_unit,
                config=dict(raw_config),
            )
        )
    return tuple(result)
