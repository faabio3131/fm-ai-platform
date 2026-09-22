"""Repositório SQLAlchemy para Billing Webhook/Reconciliation — KCA-10."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.erros import ConflitoConcorrenciaComercial

from .billing_events_orm import (
    FMBillingEventCursorORM,
    FMBillingReconciliationRunORM,
    FMBillingSubscriptionBindingORM,
    FMBillingTransactionORM,
    FMBillingWebhookInboxORM,
)


class RepositorioBillingEventsSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def adicionar_binding(
        self, row: FMBillingSubscriptionBindingORM
    ) -> FMBillingSubscriptionBindingORM:
        self._session.add(row)
        self._session.flush()
        return row

    def obter_binding_por_external(
        self,
        *,
        provider_account_id: str,
        external_subscription_ref: str,
    ) -> FMBillingSubscriptionBindingORM | None:
        return self._session.scalar(
            select(FMBillingSubscriptionBindingORM).where(
                FMBillingSubscriptionBindingORM.provider_account_id
                == provider_account_id,
                FMBillingSubscriptionBindingORM.external_subscription_ref
                == external_subscription_ref,
            )
        )

    def obter_binding_por_subscription(
        self,
        *,
        provider_account_id: str,
        subscription_id: str,
    ) -> FMBillingSubscriptionBindingORM | None:
        return self._session.scalar(
            select(FMBillingSubscriptionBindingORM).where(
                FMBillingSubscriptionBindingORM.provider_account_id
                == provider_account_id,
                FMBillingSubscriptionBindingORM.subscription_id == subscription_id,
            )
        )

    def obter_inbox_por_evento(
        self,
        *,
        provider_account_id: str,
        external_event_id: str,
    ) -> FMBillingWebhookInboxORM | None:
        return self._session.scalar(
            select(FMBillingWebhookInboxORM).where(
                FMBillingWebhookInboxORM.provider_account_id == provider_account_id,
                FMBillingWebhookInboxORM.external_event_id == external_event_id,
            )
        )

    def obter_inbox(self, inbox_id: str) -> FMBillingWebhookInboxORM | None:
        return self._session.get(FMBillingWebhookInboxORM, inbox_id)

    def adicionar_inbox(
        self, row: FMBillingWebhookInboxORM
    ) -> FMBillingWebhookInboxORM:
        self._session.add(row)
        self._session.flush()
        return row

    def atualizar_inbox(
        self,
        *,
        inbox_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> FMBillingWebhookInboxORM:
        payload = dict(values)
        payload["version"] = expected_version + 1
        result = self._session.execute(
            update(FMBillingWebhookInboxORM)
            .where(
                FMBillingWebhookInboxORM.inbox_id == inbox_id,
                FMBillingWebhookInboxORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial("billing_webhook_version_conflict")
        self._session.flush()
        row = self.obter_inbox(inbox_id)
        if row is None:
            raise ConflitoConcorrenciaComercial(
                "billing_webhook_missing_after_update"
            )
        return row

    def listar_retryable_due(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> tuple[FMBillingWebhookInboxORM, ...]:
        rows = self._session.scalars(
            select(FMBillingWebhookInboxORM)
            .where(
                FMBillingWebhookInboxORM.status == "failed_retryable",
                (
                    FMBillingWebhookInboxORM.next_retry_at.is_(None)
                    | (FMBillingWebhookInboxORM.next_retry_at <= now)
                ),
            )
            .order_by(
                FMBillingWebhookInboxORM.received_at,
                FMBillingWebhookInboxORM.inbox_id,
            )
            .limit(limit)
        ).all()
        return tuple(rows)

    def obter_transacao_por_external(
        self,
        *,
        provider_account_id: str,
        external_transaction_ref: str,
    ) -> FMBillingTransactionORM | None:
        return self._session.scalar(
            select(FMBillingTransactionORM).where(
                FMBillingTransactionORM.provider_account_id == provider_account_id,
                FMBillingTransactionORM.external_transaction_ref
                == external_transaction_ref,
            )
        )

    def obter_transacao(
        self, billing_transaction_id: str
    ) -> FMBillingTransactionORM | None:
        return self._session.get(FMBillingTransactionORM, billing_transaction_id)

    def adicionar_transacao(
        self, row: FMBillingTransactionORM
    ) -> FMBillingTransactionORM:
        self._session.add(row)
        self._session.flush()
        return row

    def atualizar_transacao(
        self,
        *,
        billing_transaction_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> FMBillingTransactionORM:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMBillingTransactionORM)
            .where(
                FMBillingTransactionORM.billing_transaction_id
                == billing_transaction_id,
                FMBillingTransactionORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial(
                "billing_transaction_version_conflict"
            )
        self._session.flush()
        row = self.obter_transacao(billing_transaction_id)
        if row is None:
            raise ConflitoConcorrenciaComercial(
                "billing_transaction_missing_after_update"
            )
        return row

    def obter_cursor(
        self,
        *,
        provider_account_id: str,
        stream_key: str,
    ) -> FMBillingEventCursorORM | None:
        return self._session.scalar(
            select(FMBillingEventCursorORM).where(
                FMBillingEventCursorORM.provider_account_id == provider_account_id,
                FMBillingEventCursorORM.stream_key == stream_key,
            )
        )

    def adicionar_cursor(
        self, row: FMBillingEventCursorORM
    ) -> FMBillingEventCursorORM:
        self._session.add(row)
        self._session.flush()
        return row

    def atualizar_cursor(
        self,
        *,
        cursor_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> FMBillingEventCursorORM:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMBillingEventCursorORM)
            .where(
                FMBillingEventCursorORM.cursor_id == cursor_id,
                FMBillingEventCursorORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise ConflitoConcorrenciaComercial(
                "billing_event_cursor_version_conflict"
            )
        self._session.flush()
        row = self._session.get(FMBillingEventCursorORM, cursor_id)
        if row is None:
            raise ConflitoConcorrenciaComercial(
                "billing_event_cursor_missing_after_update"
            )
        return row

    def adicionar_reconciliation_run(
        self, row: FMBillingReconciliationRunORM
    ) -> FMBillingReconciliationRunORM:
        self._session.add(row)
        self._session.flush()
        return row

    def atualizar_reconciliation_run(
        self,
        *,
        reconciliation_run_id: str,
        values: dict[str, object],
    ) -> FMBillingReconciliationRunORM:
        self._session.execute(
            update(FMBillingReconciliationRunORM)
            .where(
                FMBillingReconciliationRunORM.reconciliation_run_id
                == reconciliation_run_id
            )
            .values(**values)
        )
        self._session.flush()
        row = self._session.get(
            FMBillingReconciliationRunORM,
            reconciliation_run_id,
        )
        if row is None:
            raise ConflitoConcorrenciaComercial(
                "billing_reconciliation_missing_after_update"
            )
        return row
