"""Migration 0057 — Billing Configuration & Multi-Provider Routing KCA-09B."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.billing_config_orm import BillingConfigBase


def upgrade_commercial_billing_config_v1(connection: Connection) -> None:
    BillingConfigBase.metadata.create_all(bind=connection, checkfirst=True)
