from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

import migrations.legacy_expiration_alert_integrity_v1 as migration_module
from migrations.runner import (
    DEFAULT_MIGRATIONS,
    Migration,
    applied_versions,
    run_migrations,
)

_VERSION = "0028_legacy_expiration_alert_integrity_v1"
_MIGRATION = Migration(
    _VERSION,
    migration_module.upgrade_legacy_expiration_alert_integrity_v1,
)


def _legacy_engine() -> Engine:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys = ON")

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE insumos ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, nome VARCHAR UNIQUE, "
            "coluna_legada VARCHAR DEFAULT 'preservar', "
            "dias_alerta_vencimento INTEGER)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_insumos_nome_gate ON insumos (nome)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE fichas (id INTEGER PRIMARY KEY, insumo_id INTEGER, "
            "FOREIGN KEY(insumo_id) REFERENCES insumos(id))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE auditoria_insumos (insumo_id INTEGER, nome VARCHAR)"
        )
        connection.exec_driver_sql(
            "CREATE TRIGGER trg_insumos_gate AFTER INSERT ON insumos "
            "BEGIN INSERT INTO auditoria_insumos VALUES (NEW.id, NEW.nome); END"
        )
        connection.exec_driver_sql(
            "CREATE VIEW vw_insumos_gate AS SELECT id, nome FROM insumos"
        )
        connection.execute(
            text(
                "INSERT INTO insumos "
                "(id, nome, coluna_legada, dias_alerta_vencimento) VALUES "
                "(1, 'nulo', 'a', NULL), (2, 'tres', 'b', 3), "
                "(3, 'sete', 'c', 7), (4, 'quinze', 'd', 15)"
            )
        )
        connection.exec_driver_sql("INSERT INTO fichas VALUES (1, 1)")
        connection.exec_driver_sql("DELETE FROM insumos WHERE id = 4")
        connection.exec_driver_sql(
            "INSERT INTO insumos "
            "(id, nome, coluna_legada, dias_alerta_vencimento) "
            "VALUES (15, 'quinze', 'd', 15)"
        )
        connection.exec_driver_sql("DELETE FROM insumos WHERE id = 15")
        connection.exec_driver_sql("DELETE FROM auditoria_insumos")
    return engine


def test_0028_rebuild_preserves_sqlite_schema_data_and_integrity() -> None:
    engine = _legacy_engine()

    assert run_migrations(engine, migrations=(_MIGRATION,)) == (_VERSION,)
    assert run_migrations(engine, migrations=(_MIGRATION,)) == ()

    with engine.begin() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() == [
            "ok"
        ]
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        values = connection.execute(
            text(
                "SELECT id, coluna_legada, dias_alerta_vencimento "
                "FROM insumos ORDER BY id"
            )
        ).all()
        assert [tuple(row) for row in values] == [
            (1, "a", 15),
            (2, "b", 3),
            (3, "c", 7),
        ]
        column = next(
            item
            for item in inspect(connection).get_columns("insumos")
            if item["name"] == "dias_alerta_vencimento"
        )
        assert column["nullable"] is False
        assert str(column["default"]) == "15"
        assert {index["name"] for index in inspect(connection).get_indexes("insumos")} == {
            "ix_insumos_nome_gate"
        }
        assert inspect(connection).get_unique_constraints("insumos")
        assert inspect(connection).get_foreign_keys("fichas")
        assert connection.execute(text("SELECT insumo_id FROM fichas")).scalar_one() == 1
        assert connection.execute(text("SELECT COUNT(*) FROM vw_insumos_gate")).scalar_one() == 3

        sequence_before = connection.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = 'insumos'")
        ).scalar_one()
        assert sequence_before == 15
        connection.execute(text("INSERT INTO insumos (nome) VALUES ('default')"))
        inserted = connection.execute(
            text(
                "SELECT id, dias_alerta_vencimento FROM insumos "
                "WHERE nome = 'default'"
            )
        ).one()
        assert tuple(inserted) == (16, 15)
        assert connection.execute(
            text("SELECT nome FROM auditoria_insumos WHERE insumo_id = 16")
        ).scalar_one() == "default"
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO insumos (nome, dias_alerta_vencimento) "
                    "VALUES ('nulo-explicito', NULL)"
                )
            )


def test_0028_rolls_back_and_restores_foreign_keys_on_verification_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _legacy_engine()

    def _fail_verification(_connection) -> None:
        raise RuntimeError("falha injetada de integridade")

    monkeypatch.setattr(
        migration_module,
        "_verify_sqlite_integrity",
        _fail_verification,
    )
    with pytest.raises(RuntimeError, match="falha injetada"):
        run_migrations(engine, migrations=(_MIGRATION,))

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        column = next(
            item
            for item in inspect(connection).get_columns("insumos")
            if item["name"] == "dias_alerta_vencimento"
        )
        assert column["nullable"] is True
        assert column["default"] is None
        assert connection.execute(
            text(
                "SELECT dias_alerta_vencimento FROM insumos WHERE id = 1"
            )
        ).scalar_one() is None
        assert _VERSION not in applied_versions(connection)


def test_0028_preserves_sequence_when_insumos_is_empty() -> None:
    engine = _legacy_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM fichas")
        connection.exec_driver_sql("DELETE FROM insumos")
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM insumos").scalar_one() == 0
        assert connection.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = 'insumos'")
        ).scalar_one() == 15

    assert run_migrations(engine, migrations=(_MIGRATION,)) == (_VERSION,)

    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = 'insumos'")
        ).scalar_one() == 15
        connection.execute(text("INSERT INTO insumos (nome) VALUES ('apos-vazio')"))
        inserted = connection.execute(
            text(
                "SELECT id, dias_alerta_vencimento FROM insumos "
                "WHERE nome = 'apos-vazio'"
            )
        ).one()
        assert tuple(inserted) == (16, 15)
        assert connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() == [
            "ok"
        ]
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


def test_0028_fresh_and_legacy_upgrade_converge() -> None:
    fresh = create_engine("sqlite:///:memory:")
    upgrade = _legacy_engine()

    run_migrations(fresh, migrations=DEFAULT_MIGRATIONS)
    run_migrations(upgrade, migrations=(_MIGRATION,))

    with fresh.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0

    signatures = []
    for engine in (fresh, upgrade):
        column = next(
            item
            for item in inspect(engine).get_columns("insumos")
            if item["name"] == "dias_alerta_vencimento"
        )
        signatures.append(
            (str(column["type"]), column["nullable"], str(column["default"]))
        )
    assert signatures == [("INTEGER", False, "15"), ("INTEGER", False, "15")]
