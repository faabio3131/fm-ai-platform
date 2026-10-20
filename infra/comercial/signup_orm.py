"""Persistência do cadastro público KCA-06."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SignupBase(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FMPublicSignupIntentORM(SignupBase):
    __tablename__ = "fm_public_signup_intents_v1"
    __table_args__ = (
        Index("ix_fm_public_signup_email_status_v1", "owner_email", "status"),
        Index("ix_fm_public_signup_created_v1", "created_at"),
        Index("ix_fm_public_signup_corr_v1", "correlation_id"),
    )

    signup_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    primary_contact_phone: Mapped[str | None] = mapped_column(String(64))
    establishment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(96), nullable=False)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    verification_token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provisioning_id: Mapped[str | None] = mapped_column(String(64), index=True)
    resend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
