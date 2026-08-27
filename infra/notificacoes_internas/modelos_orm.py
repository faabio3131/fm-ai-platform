"""Persistência canônica e cifrada de destinatários internos."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class InternalNotificationsBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class DestinatarioNotificacaoInternaORM(InternalNotificationsBase):
    __tablename__ = "notificacao_interna_destinatarios_v1"
    __table_args__ = (
        UniqueConstraint(
            "referencia_contato",
            name="uq_notificacao_interna_referencia_v1",
        ),
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "canal",
            "contato_fingerprint",
            name="uq_notificacao_interna_scope_contato_v1",
        ),
        Index(
            "ix_notificacao_interna_scope_alerta_v1",
            "tenant_id",
            "unidade_id",
            "ativo",
            "receber_alertas_estoque",
        ),
    )

    destinatario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_exibicao: Mapped[str] = mapped_column(String(120), nullable=False)
    cargo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    canal: Mapped[str] = mapped_column(String(32), nullable=False)
    referencia_contato: Mapped[str] = mapped_column(String(128), nullable=False)
    contato_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    contato_ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    contato_mascara: Mapped[str] = mapped_column(String(32), nullable=False)
    receber_alertas_estoque: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    atualizado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
