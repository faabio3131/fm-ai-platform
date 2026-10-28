"""Persistência dos tokens de recuperação de senha do Kordena."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class PasswordRecoveryBase(DeclarativeBase):
    pass


class PasswordRecoveryTokenORM(PasswordRecoveryBase):
    __tablename__ = "fm_password_recovery_tokens_v1"
    __table_args__ = (
        UniqueConstraint(
            "token_sha256",
            name="uq_fm_password_recovery_token_hash_v1",
        ),
        Index(
            "ix_fm_password_recovery_identity_v1",
            "identity_user_id",
            "created_at",
        ),
        Index(
            "ix_fm_password_recovery_expiry_v1",
            "expires_at",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    identity_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
