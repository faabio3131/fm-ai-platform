"""Migration 0037 — amplia a estratégia de estoque da reconciliação PDV no PostgreSQL.

A migration preserva o baseline SQLite histórico. Em PostgreSQL, amplia o campo
para comportar estados semânticos do cutover como
"canonico_reservado_aguardando_producao" sem truncamento.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection


def upgrade_pdv_reconciliation_strategy_width_v1(connection: Connection) -> None:
    inspector = inspect(connection)
    table = "pdv_reconciliacoes_v1"
    column = "estoque_estrategia"

    if table not in inspector.get_table_names():
        raise RuntimeError("schema PDV sem tabela de reconciliacao")

    columns = {str(item["name"]): item for item in inspector.get_columns(table)}
    if column not in columns:
        raise RuntimeError("schema PDV sem coluna estoque_estrategia")

    current_type = columns[column]["type"]
    current_length = getattr(current_type, "length", None)
    dialect = connection.dialect.name

    if dialect == "sqlite":
        return
    if dialect != "postgresql":
        raise RuntimeError(
            "migration 0037 suporta somente PostgreSQL no runtime comercial"
        )
    if current_length is not None and int(current_length) >= 64:
        return

    connection.execute(
        text(
            "ALTER TABLE pdv_reconciliacoes_v1 "
            "ALTER COLUMN estoque_estrategia TYPE VARCHAR(64)"
        )
    )
