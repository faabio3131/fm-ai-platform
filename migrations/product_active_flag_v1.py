"""Migration 0040 — disponibilidade mínima do produto legado."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "produtos"
_COLUMN = "ativo"


def upgrade_product_active_flag_v1(connection: Connection) -> None:
    """Materializa a disponibilidade mínima do catálogo legado em ``produtos.ativo``."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("tabela produtos ausente antes da migration de disponibilidade")

    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        connection.execute(
            text(
                "ALTER TABLE produtos "
                "ADD COLUMN ativo BOOLEAN NOT NULL DEFAULT TRUE"
            )
        )
    else:
        connection.execute(
            text("UPDATE produtos SET ativo = TRUE WHERE ativo IS NULL")
        )
        if connection.dialect.name == "postgresql":
            connection.execute(
                text("ALTER TABLE produtos ALTER COLUMN ativo SET DEFAULT TRUE")
            )
            connection.execute(
                text("ALTER TABLE produtos ALTER COLUMN ativo SET NOT NULL")
            )

    final = {
        str(column["name"]): column
        for column in inspect(connection).get_columns(_TABLE)
    }
    ativo = final.get(_COLUMN)
    if ativo is None:
        raise RuntimeError("produtos.ativo ausente após migration")
    if ativo.get("nullable"):
        raise RuntimeError("produtos.ativo permaneceu anulável após migration")

    nulls = connection.execute(
        text("SELECT COUNT(*) FROM produtos WHERE ativo IS NULL")
    ).scalar_one()
    if int(nulls) != 0:
        raise RuntimeError("produtos.ativo contém valores nulos após migration")
