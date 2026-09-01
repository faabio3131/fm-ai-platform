"""Schema administrativo aditivo da Fase 5."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class AdminBase(DeclarativeBase):
    pass


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class EmpresaAdminORM(AdminBase):
    __tablename__ = "fm_empresas_admin_v1"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome_exibicao: Mapped[str] = mapped_column(String(255), nullable=False)
    moeda: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    timezone: Mapped[str] = mapped_column(
        String(80), nullable=False, default="America/Sao_Paulo"
    )
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )


class UnidadeAdminORM(AdminBase):
    __tablename__ = "fm_unidades_admin_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "codigo",
            name="uq_fm_unidade_admin_codigo_v1",
        ),
        Index(
            "ix_fm_unidade_admin_scope_active_v1",
            "tenant_id",
            "ativa",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    codigo: Mapped[str] = mapped_column(String(64), nullable=False)
    nome_fantasia: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, default="unidade")
    documento_fiscal: Mapped[str | None] = mapped_column(String(64))
    telefone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(320))
    endereco: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    horarios: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )


class ConfiguracaoEstabelecimentoORM(AdminBase):
    __tablename__ = "fm_configuracoes_estabelecimento_v1"
    __table_args__ = (
        Index(
            "ix_fm_config_estabelecimento_scope_v1",
            "tenant_id",
            "unidade_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    formas_pagamento: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    taxa_servico_percentual: Mapped[Decimal] = mapped_column(
        Numeric(7, 4), nullable=False, default=Decimal("0")
    )
    parametros_operacionais: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    politica_financeira: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict
    )
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora_utc
    )
