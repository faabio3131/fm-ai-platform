"""Migration 0035 — continuidade cifrada do runtime de canal do Assistente V1."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.assistente_atendimento.canal_schema import (
    assistente_canal_conversas_v1,
)


def upgrade_assistente_channel_runtime_v1(connection: Connection) -> None:
    assistente_canal_conversas_v1.create(
        bind=connection,
        checkfirst=True,
    )
