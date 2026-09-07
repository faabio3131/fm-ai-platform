"""Migration 0040 — disponibilidade mínima do produto legado."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "produtos"
_COLUMN = "ativo"
_SQLITE_TEMP_COLUMN = "_ativo_0040_not_null"


def upgrade_product_active_flag_v1(connection: Connection) -> None:
    """Materializa a disponibilidade mínima do catálogo legado em ``produtos.ativo``."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("tabela produtos ausente antes da migration de disponibilidade")

    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        default_sql = "1" if connection.dialect.name == "sqlite" else "TRUE"
        connection.execute(
            text(
                "ALTER TABLE produtos "
                f"ADD COLUMN ativo BOOLEAN NOT NULL DEFAULT {default_sql}"
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
        elif connection.dialect.name == "sqlite":
            ativo_existente = columns[_COLUMN]
            if ativo_existente.get("nullable") or ativo_existente.get("default") is None:
                if _SQLITE_TEMP_COLUMN in columns:
                    raise RuntimeError(
                        "coluna temporária da migration 0040 já existe em produtos"
                    )
                connection.execute(
                    text(
                        "ALTER TABLE produtos "
                        f"ADD COLUMN {_SQLITE_TEMP_COLUMN} "
                        "BOOLEAN NOT NULL DEFAULT 1"
                    )
                )
                connection.execute(
                    text(
                        f"UPDATE produtos SET {_SQLITE_TEMP_COLUMN} = "
                        "COALESCE(ativo, 1)"
                    )
                )
                connection.execute(text("ALTER TABLE produtos DROP COLUMN ativo"))
                connection.execute(
                    text(
                        "ALTER TABLE produtos "
                        f"RENAME COLUMN {_SQLITE_TEMP_COLUMN} TO ativo"
                    )
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
