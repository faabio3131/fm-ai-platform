"""Migration 0052 — Entitlement Authority e projeção local Kordena."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.entitlement_orm import EntitlementBase


def upgrade_commercial_entitlement_v1(connection: Connection) -> None:
    EntitlementBase.metadata.create_all(bind=connection, checkfirst=True)
