"""Modelos ORM canônicos de identidade, escopo e referências de segredo da V1."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
