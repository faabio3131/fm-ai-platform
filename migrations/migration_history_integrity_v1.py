"""Migration 0030 — integridade criptográfica do histórico de migrations."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from migrations.history_guard import MigrationHistoryError, assert_applied_history
from migrations.manifest import load_manifest

_TABLE = "fm_schema_migrations"
_COLUMN = "migration_sha256"


def upgrade_migration_history_integrity_v1(connection: Connection) -> None:
    """Backfill de checksums do histórico aprovado sem reescrever migrations."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("fm_schema_migrations ausente antes da migration 0030")

    columns = {str(column["name"]) for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        connection.execute(
            text(
                "ALTER TABLE fm_schema_migrations "
                "ADD COLUMN migration_sha256 VARCHAR(64) NULL"
            )
        )

    manifest = load_manifest()
    expected = {item.version: item.sha256 for item in manifest}
    versions = tuple(
        str(version)
        for version in connection.execute(
            text("SELECT version FROM fm_schema_migrations")
        ).scalars()
    )

    unknown = sorted(set(versions) - set(expected))
    if unknown:
        raise MigrationHistoryError(
            "historico aplicado contem versao desconhecida: " + ", ".join(unknown)
        )

    for version in versions:
        checksum = connection.execute(
            text(
                "SELECT migration_sha256 FROM fm_schema_migrations "
                "WHERE version = :version"
            ),
            {"version": version},
        ).scalar_one_or_none()
        expected_checksum = expected[version]
        if checksum is not None and str(checksum) != expected_checksum:
            raise MigrationHistoryError(
                f"checksum historico divergente para {version}"
            )
        if checksum is None:
            connection.execute(
                text(
                    "UPDATE fm_schema_migrations "
                    "SET migration_sha256 = :checksum "
                    "WHERE version = :version"
                ),
                {"checksum": expected_checksum, "version": version},
            )

    assert_applied_history(
        connection,
        tuple(item.version for item in manifest),
    )
