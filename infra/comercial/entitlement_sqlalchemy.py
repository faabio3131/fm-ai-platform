"""Repositório SQLAlchemy de entitlement KCA-04."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.comercial.entitlement import (
    CapabilityEntitlement,
    EstadoComercial,
    ModoAcessoComercial,
    SnapshotEntitlement,
    desserializar_capabilities,
)
from core.comercial.erros import ConflitoConcorrenciaComercial

from .entitlement_orm import (
    FMCommercialEntitlementSnapshotORM,
    KordenaEntitlementInboxORM,
    KordenaEntitlementProjectionORM,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _snapshot(row: FMCommercialEntitlementSnapshotORM) -> SnapshotEntitlement:
    return SnapshotEntitlement(
        entitlement_snapshot_id=row.entitlement_snapshot_id,
        product_account_id=row.product_account_id,
        tenant_id=row.tenant_id,
        revision=row.revision,
        commercial_state=EstadoComercial(row.commercial_state),
        plan_code=row.plan_code,
        plan_version_id=row.plan_version_id,
        access_mode=ModoAcessoComercial(row.access_mode),
        capabilities=desserializar_capabilities(dict(row.capabilities_json or {})),
        effective_from=_utc(row.effective_from),
        valid_until=_utc(row.valid_until),
        generated_at=_utc(row.generated_at),
    )


class RepositorioEntitlementSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def proxima_revisao(self, *, product_account_id: str) -> int:
        atual = self._session.scalar(
            select(func.max(FMCommercialEntitlementSnapshotORM.revision)).where(
                FMCommercialEntitlementSnapshotORM.product_account_id
                == product_account_id
            )
        )
        return int(atual or 0) + 1

    def adicionar_snapshot(
        self, row: FMCommercialEntitlementSnapshotORM
    ) -> SnapshotEntitlement:
        self._session.add(row)
        self._session.flush()
        return _snapshot(row)

    def obter_snapshot(
        self, *, entitlement_snapshot_id: str
    ) -> SnapshotEntitlement | None:
        row = self._session.get(
            FMCommercialEntitlementSnapshotORM, entitlement_snapshot_id
        )
        return _snapshot(row) if row is not None else None

    def snapshot_atual(
        self, *, product_account_id: str
    ) -> SnapshotEntitlement | None:
        row = self._session.scalar(
            select(FMCommercialEntitlementSnapshotORM)
            .where(
                FMCommercialEntitlementSnapshotORM.product_account_id
                == product_account_id
            )
            .order_by(FMCommercialEntitlementSnapshotORM.revision.desc())
            .limit(1)
        )
        return _snapshot(row) if row is not None else None

    def obter_projecao(
        self, *, tenant_id: str, product_account_id: str
    ) -> KordenaEntitlementProjectionORM | None:
        row = self._session.get(KordenaEntitlementProjectionORM, tenant_id)
        if row is None or row.product_account_id != product_account_id:
            return None
        return row

    def evento_recebido(self, *, event_id: str) -> bool:
        return self._session.get(KordenaEntitlementInboxORM, event_id) is not None

    def aplicar_evento(
        self,
        *,
        event_id: str,
        product_account_id: str,
        tenant_id: str,
        revision: int,
        commercial_state: EstadoComercial,
        plan_code: str | None,
        plan_version_id: str | None,
        access_mode: ModoAcessoComercial,
        capabilities_json: dict[str, object],
        effective_from: datetime,
        valid_until: datetime,
        received_at: datetime,
    ) -> bool:
        existente = self._session.get(KordenaEntitlementProjectionORM, tenant_id)
        applied = False
        if existente is None:
            existente = KordenaEntitlementProjectionORM(
                tenant_id=tenant_id,
                product_account_id=product_account_id,
                revision=revision,
                commercial_state=commercial_state.value,
                plan_code=plan_code,
                plan_version_id=plan_version_id,
                access_mode=access_mode.value,
                capabilities_json=capabilities_json,
                effective_from=effective_from,
                valid_until=valid_until,
                last_synced_at=received_at,
            )
            self._session.add(existente)
            applied = True
        elif existente.product_account_id != product_account_id:
            raise ConflitoConcorrenciaComercial("tenant_product_account_conflict")
        elif revision > existente.revision:
            existente.revision = revision
            existente.commercial_state = commercial_state.value
            existente.plan_code = plan_code
            existente.plan_version_id = plan_version_id
            existente.access_mode = access_mode.value
            existente.capabilities_json = capabilities_json
            existente.effective_from = effective_from
            existente.valid_until = valid_until
            existente.last_synced_at = received_at
            applied = True

        self._session.add(
            KordenaEntitlementInboxORM(
                event_id=event_id,
                product_account_id=product_account_id,
                tenant_id=tenant_id,
                revision=revision,
                applied=applied,
                received_at=received_at,
            )
        )
        self._session.flush()
        return applied

    def capabilities_projecao(
        self, row: KordenaEntitlementProjectionORM
    ) -> tuple[CapabilityEntitlement, ...]:
        return desserializar_capabilities(dict(row.capabilities_json or {}))
