"""Migration 0065 — vínculo de identidade federada Google."""

from __future__ import annotations

from infra.seguranca.federated_identity_orm import FederatedIdentityBase


def upgrade_google_federated_identity_v1(connection) -> None:
    FederatedIdentityBase.metadata.create_all(bind=connection, checkfirst=True)
