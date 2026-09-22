"""Migration 0056 — Subscription Engine KCA-08."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.subscription_orm import SubscriptionBase


def upgrade_commercial_subscription_v1(connection: Connection) -> None:
    SubscriptionBase.metadata.create_all(bind=connection, checkfirst=True)
