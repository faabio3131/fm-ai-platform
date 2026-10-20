"""Migration 0058 — Billing Webhook Inbox + Reconciliation KCA-10."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.billing_events_orm import BillingEventsBase


def upgrade_commercial_billing_events_v1(connection: Connection) -> None:
    BillingEventsBase.metadata.create_all(bind=connection, checkfirst=True)
