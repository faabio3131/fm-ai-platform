"""ORM da identidade publica do Cardapio Digital V1."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CardapioPublicoBase(DeclarativeBase):
    pass


class PublicacaoCardapioORM(CardapioPublicoBase):
    __tablename__ = "fm_cardapio_publico_v1"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "unidade_id",
            name="uq_fm_cardapio_publico_v1_escopo",
        ),
    )

    public_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    unidade_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    publicada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    versao: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
