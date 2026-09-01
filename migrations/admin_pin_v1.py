"""Migration aditiva para PIN administrativo individual da V1."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "fm_usuarios_v1"
_COLUMN = "admin_pin_hash"


def upgrade_admin_pin_v1(connection: Connection) -> None:
    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("tabela fm_usuarios_v1 ausente antes da migration de PIN")
    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN in columns:
        return
    connection.execute(
        text(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} VARCHAR(512) NULL")
    )
