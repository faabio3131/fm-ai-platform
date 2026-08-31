"""Persistência canônica da política de entrega por tenant/unidade."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DeliveryPolicyBase(DeclarativeBase):
    pass


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class OrigemEntregaORM(DeliveryPolicyBase):
    __tablename__ = "delivery_origem_unidade_v1"
    __table_args__ = (
        CheckConstraint("versao >= 1", name="ck_delivery_origem_versao_v1"),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    endereco_texto: Mapped[str] = mapped_column(Text, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora
    )


class AreaEntregaORM(DeliveryPolicyBase):
    __tablename__ = "delivery_areas_v1"
    __table_args__ = (
        CheckConstraint("versao >= 1", name="ck_delivery_area_versao_v1"),
        CheckConstraint("taxa >= 0", name="ck_delivery_area_taxa_v1"),
        CheckConstraint("sla_minutos >= 1", name="ck_delivery_area_sla_min_v1"),
        CheckConstraint(
            "sla_maxutos >= sla_minutos",
            name="ck_delivery_area_sla_intervalo_v1",
        ),
        Index(
            "ix_delivery_areas_scope_v1",
            "tenant_id",
            "unidade_id",
            "ativa",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    unidade_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    area_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    prefixos_cep: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    taxa: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    sla_minutos: Mapped[int] = mapped_column(Integer, nullable=False)
    sla_maxutos: Mapped[int] = mapped_column(Integer, nullable=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_agora
    )
