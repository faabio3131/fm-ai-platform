"""Modelos ORM canônicos de identidade, escopo, segredos e auditoria da V1."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class SecurityBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class UsuarioSegurancaORM(SecurityBase):
    __tablename__ = "fm_usuarios_v1"

    usuario_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unidade_padrao_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc, onupdate=_agora_utc
    )


class UsuarioPapelORM(SecurityBase):
    __tablename__ = "fm_usuario_papeis_v1"
    __table_args__ = (
        UniqueConstraint("usuario_id", "papel", name="uq_fm_usuario_papel_v1"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(
        ForeignKey("fm_usuarios_v1.usuario_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    papel: Mapped[str] = mapped_column(String(64), nullable=False)


class UsuarioUnidadeORM(SecurityBase):
    __tablename__ = "fm_usuario_unidades_v1"
    __table_args__ = (
        UniqueConstraint("usuario_id", "unidade_id", name="uq_fm_usuario_unidade_v1"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[str] = mapped_column(
        ForeignKey("fm_usuarios_v1.usuario_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


class CredencialReferenciaORM(SecurityBase):
    """Histórico append-only de referências; nunca armazena o segredo resolvido."""

    __tablename__ = "fm_credenciais_referencias_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "provedor",
            "finalidade",
            "versao",
            name="uq_fm_credencial_ref_versao_v1",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provedor: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    finalidade: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    referencia: Mapped[str] = mapped_column(String(512), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rotacionada_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    desativada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventoAuditoriaORM(SecurityBase):
    """Trilha append-only de ações autorizadas/recusadas do domínio."""

    __tablename__ = "fm_auditoria_v1"
    __table_args__ = (
        Index("ix_fm_auditoria_scope_time_v1", "tenant_id", "unidade_id", "timestamp"),
        Index("ix_fm_auditoria_corr_v1", "correlation_id"),
        Index("ix_fm_auditoria_recurso_v1", "recurso_tipo", "recurso_id"),
    )

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    unidade_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    usuario_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    papel_efetivo: Mapped[str | None] = mapped_column(String(64))
    acao: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    recurso_tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    recurso_id: Mapped[str | None] = mapped_column(String(128))
    resultado: Mapped[str] = mapped_column(String(32), nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origem: Mapped[str] = mapped_column(String(64), nullable=False)
    politica: Mapped[str] = mapped_column(String(128), nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    causation_id: Mapped[str | None] = mapped_column(String(128))
    antes_resumido: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    depois_resumido: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metadata_segura: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
