"""Persistência cifrada de segredos de integrações por tenant/unidade.

O valor em claro nunca é persistido. A chave mestra permanece na infraestrutura
(`FM_AI_SECRET_MASTER_KEY`) e somente o ciphertext é armazenado no banco.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SecretVaultBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class SegredoIntegracaoORM(SecretVaultBase):
    __tablename__ = "fm_segredos_integracoes_v1"
    __table_args__ = (
        Index(
            "ix_fm_segredos_integracoes_scope_v1",
            "tenant_id",
            "unidade_id",
            "provedor",
            "finalidade",
        ),
    )

    referencia: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provedor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    finalidade: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    criado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
