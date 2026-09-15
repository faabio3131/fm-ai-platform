"""Migration 0041 — identidade publica configuravel do Cardapio Digital V1."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.cardapio_publico.modelos_orm import CardapioPublicoBase


def upgrade_cardapio_publico_identity_v1(connection: Connection) -> None:
    CardapioPublicoBase.metadata.create_all(bind=connection, checkfirst=True)
