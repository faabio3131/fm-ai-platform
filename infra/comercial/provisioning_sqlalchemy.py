"""Repositório SQLAlchemy da Saga de provisionamento KCA-05."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.provisioning import EstadoProvisionamento, ProvisionamentoKordena

from .provisioning_orm import (
    FMCommercialProvisioningInboxORM,
    FMCommercialProvisioningSagaORM,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _model(row: FMCommercialProvisioningSagaORM) -> ProvisionamentoKordena:
    return ProvisionamentoKordena(
        provisioning_id=row.provisioning_id,
        idempotency_key=row.idempotency_key,
        request_sha256=row.request_sha256,
        status=EstadoProvisionamento(row.status),
        current_step=row.current_step,
        fm_customer_id=row.fm_customer_id,
        product_account_id=row.product_account_id,
        identity_user_id=row.identity_user_id,
        membership_id=row.membership_id,
        tenant_id=row.tenant_id,
        unidade_id=row.unidade_id,
        owner_email=row.owner_email,
        display_name=row.display_name,
        primary_contact_phone=row.primary_contact_phone,
        trial_binding_status=row.trial_binding_status,
        entitlement_snapshot_id=row.entitlement_snapshot_id,
        attempts=row.attempts,
        last_error=row.last_error,
        version=row.version,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
    )


class RepositorioProvisioningSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, provisioning_id: str) -> ProvisionamentoKordena | None:
        row = self._session.get(FMCommercialProvisioningSagaORM, provisioning_id)
        return _model(row) if row is not None else None

    def obter_por_idempotencia(self, key: str) -> ProvisionamentoKordena | None:
        row = self._session.scalar(
            select(FMCommercialProvisioningSagaORM).where(
                FMCommercialProvisioningSagaORM.idempotency_key == key
            )
        )
        return _model(row) if row is not None else None

    def adicionar(
        self, row: FMCommercialProvisioningSagaORM
    ) -> ProvisionamentoKordena:
        self._session.add(row)
        self._session.flush()
        return _model(row)

    def atualizar(
        self,
        *,
        provisioning_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> ProvisionamentoKordena:
        values = dict(values)
        values["version"] = expected_version + 1
        values["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMCommercialProvisioningSagaORM)
            .where(
                FMCommercialProvisioningSagaORM.provisioning_id == provisioning_id,
                FMCommercialProvisioningSagaORM.version == expected_version,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("provisioning_concurrency_conflict")
        self._session.flush()
        atual = self.obter(provisioning_id)
        if atual is None:
            raise RuntimeError("provisioning_missing_after_update")
        return atual

    def registrar_evento_recebido(
        self,
        *,
        event_id: str,
        provisioning_id: str,
        event_type: str,
    ) -> bool:
        if self._session.get(FMCommercialProvisioningInboxORM, event_id) is not None:
            return False
        self._session.add(
            FMCommercialProvisioningInboxORM(
                event_id=event_id,
                provisioning_id=provisioning_id,
                event_type=event_type,
                received_at=datetime.now(timezone.utc),
            )
        )
        self._session.flush()
        return True
