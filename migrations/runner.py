"""Runner mínimo, versionado e idempotente para migrations comerciais V1.

As migrations históricas do projeto foram deliberadamente restritas ao SQLite E2E.
Este runner cria uma trilha separada para evolução de schema em bancos reais, sem
executar downgrade destrutivo automaticamente.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Engine, MetaData, String, Table, insert, select
from sqlalchemy.engine import Connection

from infra.legacy_schema import legacy_metadata
from infra.seguranca.modelos_orm import CredencialReferenciaORM, SecurityBase

_metadata = MetaData()
_schema_migrations = Table(
    "fm_schema_migrations",
    _metadata,
    Column("version", String(128), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


@dataclass(frozen=True)
class Migration:
    version: str
    apply: Callable[[Connection], None]

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("migration sem versao")


def _security_identity_v1(connection: Connection) -> None:
    SecurityBase.metadata.create_all(bind=connection, checkfirst=True)


def _credential_references_v1(connection: Connection) -> None:
    CredencialReferenciaORM.__table__.create(bind=connection, checkfirst=True)


def _legacy_app_schema_v1(connection: Connection) -> None:
    legacy_metadata.create_all(bind=connection, checkfirst=True)


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (
    Migration("0001_security_identity_v1", _security_identity_v1),
    Migration("0002_credential_references_v1", _credential_references_v1),
    Migration("0003_legacy_app_schema_v1", _legacy_app_schema_v1),
)


def applied_versions(connection: Connection) -> frozenset[str]:
    _metadata.create_all(bind=connection, checkfirst=True)
    return frozenset(connection.execute(select(_schema_migrations.c.version)).scalars())


def pending_versions(engine: Engine) -> tuple[str, ...]:
    with engine.begin() as connection:
        applied = applied_versions(connection)
    return tuple(
        migration.version
        for migration in DEFAULT_MIGRATIONS
        if migration.version not in applied
    )


def assert_schema_current(engine: Engine) -> None:
    pending = pending_versions(engine)
    if pending:
        versions = ", ".join(pending)
        raise RuntimeError(
            "Schema comercial desatualizado. Execute python -m scripts.migrate_v1. "
            f"Migrations pendentes: {versions}"
        )


def run_migrations(
    engine: Engine, migrations: Iterable[Migration] = DEFAULT_MIGRATIONS
) -> tuple[str, ...]:
    """Aplica migrations pendentes em ordem, uma transação por migration."""

    ordered = tuple(migrations)
    versions = [migration.version for migration in ordered]
    if len(versions) != len(set(versions)):
        raise ValueError("versao de migration duplicada")

    applied_now: list[str] = []
    with engine.begin() as connection:
        already = set(applied_versions(connection))

    for migration in ordered:
        if migration.version in already:
            continue
        with engine.begin() as connection:
            current = set(applied_versions(connection))
            if migration.version in current:
                continue
            migration.apply(connection)
            connection.execute(
                insert(_schema_migrations).values(
                    version=migration.version,
                    applied_at=datetime.now(timezone.utc),
                )
            )
        already.add(migration.version)
        applied_now.append(migration.version)

    return tuple(applied_now)
