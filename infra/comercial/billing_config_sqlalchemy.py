"""Repositório SQLAlchemy de billing configuration — KCA-09B."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.billing_config import (
    BillingConnectionTestStatus,
    BillingEnvironment,
    BillingPaymentMethod,
    BillingProviderAccount,
    BillingProviderAccountStatus,
    BillingRoutingPolicy,
)
from core.comercial.erros import ConflitoConcorrenciaComercial

from .billing_config_orm import (
    FMBillingProviderAccountORM,
    FMBillingRoutingPolicyORM,
)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _provider_account(row: FMBillingProviderAccountORM) -> BillingProviderAccount:
    return BillingProviderAccount(
        provider_account_id=row.provider_account_id,
        provider_code=row.provider_code,
        display_name=row.display_name,
        legal_entity_ref=row.legal_entity_ref,
        environment=BillingEnvironment(row.environment),
        status=BillingProviderAccountStatus(row.status),
        credential_secret_reference=row.credential_secret_reference,
        supported_payment_methods=tuple(
            BillingPaymentMethod(item) for item in row.supported_payment_methods
        ),
        supports_recurring=row.supports_recurring,
        supports_webhooks=row.supports_webhooks,
        priority=row.priority,
        last_tested_at=_utc(row.last_tested_at),
        last_test_status=BillingConnectionTestStatus(row.last_test_status),
        version=row.version,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


def _routing_policy(row: FMBillingRoutingPolicyORM) -> BillingRoutingPolicy:
    return BillingRoutingPolicy(
        routing_policy_id=row.routing_policy_id,
        product_code=row.product_code,
        payment_method=BillingPaymentMethod(row.payment_method),
        environment=BillingEnvironment(row.environment),
        primary_provider_account_id=row.primary_provider_account_id,
        fallback_provider_account_ids=tuple(row.fallback_provider_account_ids),
        active=row.active,
        version=row.version,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),  # type: ignore[arg-type]
        updated_at=_utc(row.updated_at),  # type: ignore[arg-type]
    )


class RepositorioBillingConfigSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def adicionar_provider_account(
        self, row: FMBillingProviderAccountORM
    ) -> BillingProviderAccount:
        self._session.add(row)
        self._session.flush()
        return _provider_account(row)

    def obter_provider_account(
        self, provider_account_id: str
    ) -> BillingProviderAccount | None:
        row = self._session.get(FMBillingProviderAccountORM, provider_account_id)
        return _provider_account(row) if row is not None else None

    def listar_provider_accounts(self) -> tuple[BillingProviderAccount, ...]:
        rows = self._session.scalars(
            select(FMBillingProviderAccountORM).order_by(
                FMBillingProviderAccountORM.environment,
                FMBillingProviderAccountORM.priority,
                FMBillingProviderAccountORM.provider_code,
                FMBillingProviderAccountORM.provider_account_id,
            )
        ).all()
        return tuple(_provider_account(row) for row in rows)

    def atualizar_provider_account(
        self,
        *,
        provider_account_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> BillingProviderAccount:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMBillingProviderAccountORM)
            .where(
                FMBillingProviderAccountORM.provider_account_id
                == provider_account_id,
                FMBillingProviderAccountORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial(
                "billing_provider_account_version_conflict"
            )
        self._session.flush()
        current = self.obter_provider_account(provider_account_id)
        if current is None:
            raise ConflitoConcorrenciaComercial(
                "billing_provider_account_missing_after_update"
            )
        return current

    def adicionar_routing_policy(
        self, row: FMBillingRoutingPolicyORM
    ) -> BillingRoutingPolicy:
        self._session.add(row)
        self._session.flush()
        return _routing_policy(row)

    def obter_routing_policy(
        self, routing_policy_id: str
    ) -> BillingRoutingPolicy | None:
        row = self._session.get(FMBillingRoutingPolicyORM, routing_policy_id)
        return _routing_policy(row) if row is not None else None

    def obter_routing_policy_scope(
        self,
        *,
        product_code: str,
        payment_method: BillingPaymentMethod,
        environment: BillingEnvironment,
    ) -> BillingRoutingPolicy | None:
        row = self._session.scalar(
            select(FMBillingRoutingPolicyORM).where(
                FMBillingRoutingPolicyORM.product_code == product_code,
                FMBillingRoutingPolicyORM.payment_method == payment_method.value,
                FMBillingRoutingPolicyORM.environment == environment.value,
            )
        )
        return _routing_policy(row) if row is not None else None

    def listar_routing_policies(self) -> tuple[BillingRoutingPolicy, ...]:
        rows = self._session.scalars(
            select(FMBillingRoutingPolicyORM).order_by(
                FMBillingRoutingPolicyORM.product_code,
                FMBillingRoutingPolicyORM.environment,
                FMBillingRoutingPolicyORM.payment_method,
            )
        ).all()
        return tuple(_routing_policy(row) for row in rows)

    def atualizar_routing_policy(
        self,
        *,
        routing_policy_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> BillingRoutingPolicy:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMBillingRoutingPolicyORM)
            .where(
                FMBillingRoutingPolicyORM.routing_policy_id == routing_policy_id,
                FMBillingRoutingPolicyORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial(
                "billing_routing_policy_version_conflict"
            )
        self._session.flush()
        current = self.obter_routing_policy(routing_policy_id)
        if current is None:
            raise ConflitoConcorrenciaComercial(
                "billing_routing_policy_missing_after_update"
            )
        return current
