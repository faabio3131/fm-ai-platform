"""Migration aditiva do cofre cifrado de credenciais das integrações V1."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.seguranca.segredos_orm import SecretVaultBase


def upgrade_integration_secret_vault_v1(connection: Connection) -> None:
    SecretVaultBase.metadata.create_all(bind=connection, checkfirst=True)
