"""Persistência cifrada dos contatos de ClienteCRM."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class ContactVaultBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class ContatoSeguroORM(ContactVaultBase):
    __tablename__ = "crm_contatos_seguros_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "canal",
            "valor_hash",
            name="uq_crm_contato_scope_hash_v1",
        ),
        Index(
            "ix_crm_contato_scope_v1",
            "tenant_id",
            "unidade_id",
            "canal",
        ),
    )

    referencia: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    unidade_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    canal: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    valor_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    ciphertext: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    criado_por: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    correlation_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_agora_utc,
    )
