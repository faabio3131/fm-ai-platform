"""Domínio da Saga de provisionamento comercial KCA-05."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EstadoProvisionamento(StrEnum):
    REQUESTED = "requested"
    VALIDATING = "validating"
    PROVISIONING = "provisioning"
    FAILED_RETRYABLE = "failed_retryable"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    READY = "ready"


_TRANSICOES: dict[EstadoProvisionamento, frozenset[EstadoProvisionamento]] = {
    EstadoProvisionamento.REQUESTED: frozenset(
        {EstadoProvisionamento.VALIDATING, EstadoProvisionamento.COMPENSATING}
    ),
    EstadoProvisionamento.VALIDATING: frozenset(
        {
            EstadoProvisionamento.PROVISIONING,
            EstadoProvisionamento.FAILED_RETRYABLE,
            EstadoProvisionamento.COMPENSATING,
        }
    ),
    EstadoProvisionamento.PROVISIONING: frozenset(
        {
            EstadoProvisionamento.READY,
            EstadoProvisionamento.FAILED_RETRYABLE,
            EstadoProvisionamento.COMPENSATING,
        }
    ),
    EstadoProvisionamento.FAILED_RETRYABLE: frozenset(
        {EstadoProvisionamento.VALIDATING, EstadoProvisionamento.COMPENSATING}
    ),
    EstadoProvisionamento.COMPENSATING: frozenset(
        {EstadoProvisionamento.COMPENSATED, EstadoProvisionamento.FAILED_RETRYABLE}
    ),
    EstadoProvisionamento.COMPENSATED: frozenset(),
    EstadoProvisionamento.READY: frozenset(),
}


def validar_transicao(
    atual: EstadoProvisionamento,
    destino: EstadoProvisionamento,
) -> None:
    if destino == atual:
        return
    if destino not in _TRANSICOES[atual]:
        raise ValueError(
            f"provisioning_transition_invalid:{atual.value}->{destino.value}"
        )


@dataclass(frozen=True, kw_only=True)
class ProvisionamentoKordena:
    provisioning_id: str
    idempotency_key: str
    request_sha256: str
    status: EstadoProvisionamento
    current_step: str
    fm_customer_id: str | None
    product_account_id: str | None
    identity_user_id: str | None
    membership_id: str | None
    tenant_id: str
    unidade_id: str
    owner_email: str
    display_name: str
    primary_contact_phone: str | None
    trial_binding_status: str
    entitlement_snapshot_id: str | None
    attempts: int
    last_error: str | None
    version: int
    correlation_id: str
    created_at: datetime
    updated_at: datetime
