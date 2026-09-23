"""Repositório SQLAlchemy do Subscription Engine KCA-08."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.erros import ConflitoConcorrenciaComercial
from core.comercial.subscription import AssinaturaComercial, EstadoAssinatura

from .subscription_orm import FMCommercialSubscriptionORM


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _subscription(row: FMCommercialSubscriptionORM) -> AssinaturaComercial:
    return AssinaturaComercial(
        subscription_id=row.subscription_id,
        fm_customer_id=row.fm_customer_id,
        product_account_id=row.product_account_id,
        tenant_id=row.tenant_id,
        plan_code=row.plan_code,
        plan_version_id=row.plan_version_id,
        price_id=row.price_id,
        currency=row.currency,
        billing_period=row.billing_period,
        contracted_amount=Decimal(row.contracted_amount),
        status=EstadoAssinatura(row.status),
        current_period_start=_utc(row.current_period_start),
        current_period_end=_utc(row.current_period_end),
        cancel_at_period_end=row.cancel_at_period_end,
        canceled_at=_utc(row.canceled_at),
        activated_at=_utc(row.activated_at),
        suspended_at=_utc(row.suspended_at),
        version=row.version,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


class RepositorioSubscriptionComercialSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, subscription_id: str) -> AssinaturaComercial | None:
        row = self._session.get(FMCommercialSubscriptionORM, subscription_id)
        return _subscription(row) if row is not None else None

    def obter_por_product_account(
        self,
        product_account_id: str,
    ) -> AssinaturaComercial | None:
        row = self._session.scalar(
            select(FMCommercialSubscriptionORM).where(
                FMCommercialSubscriptionORM.product_account_id == product_account_id
            )
        )
        return _subscription(row) if row is not None else None

    def adicionar(
        self,
        row: FMCommercialSubscriptionORM,
    ) -> AssinaturaComercial:
        self._session.add(row)
        self._session.flush()
        return _subscription(row)

    def atualizar(
        self,
        *,
        subscription_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> AssinaturaComercial:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMCommercialSubscriptionORM)
            .where(
                FMCommercialSubscriptionORM.subscription_id == subscription_id,
                FMCommercialSubscriptionORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial("subscription_version_conflict")
        self._session.flush()
        current = self.obter(subscription_id)
        if current is None:
            raise ConflitoConcorrenciaComercial(
                "subscription_missing_after_update"
            )
        return current
