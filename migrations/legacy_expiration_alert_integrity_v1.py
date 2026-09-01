"""Migration 0028 — integridade do alerta de validade do catálogo legado."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "insumos"
_COLUMN = "dias_alerta_vencimento"
_DEFAULT = 15
_SQLITE_NEW_TABLE = "insumos_sd_adr_014_new"


@dataclass(frozen=True)
class _SQLiteObject:
    object_type: str
    name: str
    sql: str


def _quote_sqlite(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sqlite_table_sql_with_integrity(table_sql: str) -> str:
    create_pattern = re.compile(
        r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:(?:\"[^\"]+\"|`[^`]+`|\[[^]]+\]|\w+)\s*\.\s*)?"
        r"(?:\"insumos\"|`insumos`|\[insumos\]|insumos)",
        re.IGNORECASE,
    )
    rebuilt_sql, table_replacements = create_pattern.subn(
        f'CREATE TABLE {_quote_sqlite(_SQLITE_NEW_TABLE)}',
        table_sql,
        count=1,
    )
    column_pattern = re.compile(
        rf'(?P<prefix>(?:"{_COLUMN}"|`{_COLUMN}`|\[{_COLUMN}\]|{_COLUMN})\s+INTEGER)'
        r'(?P<suffix>\s*(?=,|\)))',
        re.IGNORECASE,
    )
    rebuilt_sql, column_replacements = column_pattern.subn(
        rf"\g<prefix> DEFAULT {_DEFAULT} NOT NULL\g<suffix>",
        rebuilt_sql,
        count=1,
    )
    if table_replacements != 1 or column_replacements != 1:
        raise RuntimeError(
            "definição SQLite de insumos.dias_alerta_vencimento não suportada"
        )
    return rebuilt_sql


def _sqlite_dependent_objects(connection: Connection) -> tuple[_SQLiteObject, ...]:
    rows = connection.execute(
        text(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE tbl_name = :table AND type IN ('index', 'trigger') "
            "AND sql IS NOT NULL ORDER BY type, name"
        ),
        {"table": _TABLE},
    ).all()
    return tuple(
        _SQLiteObject(str(row.type), str(row.name), str(row.sql)) for row in rows
    )


def _sqlite_views(connection: Connection) -> tuple[_SQLiteObject, ...]:
    rows = connection.execute(
        text(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type = 'view' AND sql IS NOT NULL ORDER BY name"
        )
    ).all()
    return tuple(
        _SQLiteObject(str(row.type), str(row.name), str(row.sql)) for row in rows
    )


def _sqlite_sequence(connection: Connection) -> int | None:
    exists = connection.execute(
        text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'sqlite_sequence'"
        )
    ).scalar_one_or_none()
    if exists is None:
        return None
    value = connection.execute(
        text("SELECT seq FROM sqlite_sequence WHERE name = :name"),
        {"name": _TABLE},
    ).scalar_one_or_none()
    return None if value is None else int(value)


def _verify_sqlite_integrity(connection: Connection) -> None:
    integrity_rows = tuple(
        str(value) for value in connection.exec_driver_sql("PRAGMA integrity_check").scalars()
    )
    if integrity_rows != ("ok",):
        raise RuntimeError(
            "PRAGMA integrity_check divergiu: " + repr(integrity_rows)
        )
    foreign_key_rows = tuple(
        connection.exec_driver_sql("PRAGMA foreign_key_check").all()
    )
    if foreign_key_rows:
        raise RuntimeError(
            "PRAGMA foreign_key_check encontrou violações: "
            + repr(foreign_key_rows)
        )


def _rebuild_sqlite_insumos(connection: Connection) -> None:
    if int(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()) != 0:
        raise RuntimeError(
            "migration 0028 SQLite exige foreign_keys desabilitado antes da transação"
        )

    table_sql = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": _TABLE},
    ).scalar_one()
    dependent_objects = _sqlite_dependent_objects(connection)
    views = _sqlite_views(connection)
    sequence = _sqlite_sequence(connection)
    columns = tuple(str(column["name"]) for column in inspect(connection).get_columns(_TABLE))
    quoted_columns = ", ".join(_quote_sqlite(column) for column in columns)

    connection.exec_driver_sql(_sqlite_table_sql_with_integrity(str(table_sql)))
    connection.exec_driver_sql(
        f"INSERT INTO {_quote_sqlite(_SQLITE_NEW_TABLE)} ({quoted_columns}) "
        f"SELECT {quoted_columns} FROM {_quote_sqlite(_TABLE)}"
    )
    for view in reversed(views):
        connection.exec_driver_sql(f"DROP VIEW {_quote_sqlite(view.name)}")
    connection.exec_driver_sql(f"DROP TABLE {_quote_sqlite(_TABLE)}")
    connection.exec_driver_sql(
        f"ALTER TABLE {_quote_sqlite(_SQLITE_NEW_TABLE)} "
        f"RENAME TO {_quote_sqlite(_TABLE)}"
    )

    for item in dependent_objects:
        connection.exec_driver_sql(item.sql)
    for view in views:
        connection.exec_driver_sql(view.sql)
    if sequence is not None:
        connection.execute(
            text("DELETE FROM sqlite_sequence WHERE name = :name"),
            {"name": _TABLE},
        )
        connection.execute(
            text("INSERT INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"),
            {"seq": sequence, "name": _TABLE},
        )
        restored_sequence = connection.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = :name"),
            {"name": _TABLE},
        ).scalar_one_or_none()
        if restored_sequence != sequence:
            raise RuntimeError(
                "sqlite_sequence de insumos não foi restaurada integralmente"
            )
    current_views = {item.name: item.sql for item in _sqlite_views(connection)}
    for view in views:
        if current_views.get(view.name) != view.sql:
            raise RuntimeError(f"view SQLite não preservada: {view.name}")

    _verify_sqlite_integrity(connection)


def upgrade_legacy_expiration_alert_integrity_v1(connection: Connection) -> None:
    """Materializa 15 para omissões e impede novos NULL sem tocar outros valores."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("tabela insumos ausente antes da migration 0028")
    columns = {str(column["name"]): column for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        raise RuntimeError(
            "insumos.dias_alerta_vencimento ausente antes da migration 0028"
        )

    connection.execute(
        text(
            "UPDATE insumos SET dias_alerta_vencimento = :default "
            "WHERE dias_alerta_vencimento IS NULL"
        ),
        {"default": _DEFAULT},
    )

    if connection.dialect.name == "postgresql":
        connection.execute(
            text(
                "ALTER TABLE insumos ALTER COLUMN dias_alerta_vencimento "
                "SET DEFAULT 15"
            )
        )
        connection.execute(
            text(
                "ALTER TABLE insumos ALTER COLUMN dias_alerta_vencimento "
                "SET NOT NULL"
            )
        )
    elif connection.dialect.name == "sqlite":
        column = columns[_COLUMN]
        if column.get("nullable", True) or str(column.get("default")) != "15":
            _rebuild_sqlite_insumos(connection)
        else:
            _verify_sqlite_integrity(connection)
    else:
        raise RuntimeError(
            f"dialeto não suportado pela migration 0028: {connection.dialect.name}"
        )
