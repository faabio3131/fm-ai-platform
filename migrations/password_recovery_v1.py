"""Migration 0064 — recuperação segura de senha Kordena."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.seguranca.password_recovery_orm import PasswordRecoveryBase


def upgrade_password_recovery_v1(connection: Connection) -> None:
    PasswordRecoveryBase.metadata.create_all(bind=connection, checkfirst=True)
