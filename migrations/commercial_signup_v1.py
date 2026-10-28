"""Migration 0054 — Public Signup + Verification KCA-06."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.comercial.signup_orm import SignupBase


def upgrade_commercial_signup_v1(connection: Connection) -> None:
    SignupBase.metadata.create_all(bind=connection, checkfirst=True)
