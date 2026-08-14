"""Persistência aditiva das configurações externas por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class IntegrationConfigBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class ServicoExternoConfigORM(IntegrationConfigBase):
    __tablename__ = "fm_servicos_externos_config_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            "servico",
            "provedor",
            "conta_externa",
            name="uq_fm_servico_externo_conta_v1",
        ),
        Index(
            "ix_fm_servico_externo_scope_v1",
            "tenant_id",
            "unidade_id",
            "habilitada",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    configuracao_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    servico: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    provedor: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    conta_externa: Mapped[str] = mapped_column(String(256), nullable=False)
    ambiente: Mapped[str] = mapped_column(String(32), nullable=False)
    parametros_publicos: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    finalidades_credenciais: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    habilitada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    homologada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidencia_homologacao_ref: Mapped[str | None] = mapped_column(String(512))
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    atualizado_por: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
