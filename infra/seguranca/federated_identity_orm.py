"""Vínculos persistentes entre identidade Kordena e provedores federados."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class FederatedIdentityBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class FederatedIdentityORM(FederatedIdentityBase):
    __tablename__ = "fm_federated_identities_v1"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_subject",
            name="uq_fm_federated_provider_subject_v1",
        ),
        UniqueConstraint(
            "provider",
            "identity_user_id",
            name="uq_fm_federated_provider_identity_v1",
        ),
        Index("ix_fm_federated_identity_v1", "identity_user_id"),
    )

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    identity_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email_at_link: Mapped[str] = mapped_column(String(320), nullable=False)
    hosted_domain: Mapped[str | None] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
