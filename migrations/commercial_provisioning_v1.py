"""Migration 0053 — Tenant Provisioning Saga KCA-05."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.provisioning_orm import ProvisioningBase


def upgrade_commercial_provisioning_v1(connection: Connection) -> None:
    ProvisioningBase.metadata.create_all(bind=connection, checkfirst=True)
