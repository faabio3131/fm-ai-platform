"""Runner mínimo, versionado e idempotente para migrations comerciais V1.

As migrations históricas do projeto foram deliberadamente restritas ao SQLite E2E.
Este runner cria uma trilha separada para evolução de schema em bancos reais, sem
executar downgrade destrutivo automaticamente.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    delete,
    insert,
    select,
)
from sqlalchemy.engine import Connection

from core.entrega.modelos_orm import DeliveryBase
from core.estoque.modelos_orm import StockBase
from core.impressao.modelos_orm import ImpressaoBase
from core.kds.modelos_orm import KDSBase
from core.pagamentos.modelos_orm import PaymentsBase
from core.pdv.modelos_orm import PDVBase
from core.pedidos.modelos_orm import OrdersBase
from core.salao.modelos_orm import SalaoBase
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import CoreRuntimeBase
from infra.integracoes.modelos_orm import IntegrationConfigBase
from infra.legacy_schema import legacy_metadata
from infra.seguranca.modelos_orm import (
    CredencialReferenciaORM,
    EventoAuditoriaORM,
    SecurityBase,
)
from migrations.admin_access_authorization_v1 import (
    upgrade_admin_access_authorization_v1,
)
from migrations.admin_pin_v1 import upgrade_admin_pin_v1
from migrations.integration_secret_vault_v1 import upgrade_integration_secret_vault_v1
from migrations.legacy_schema_reconciliation_v1 import reconcile_legacy_schema_v1
from migrations.legacy_schema_upgrade_v1 import upgrade_legacy_schema_v1

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
    revert: Callable[[Connection], None] | None = None

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("migration sem versao")


def _security_identity_v1(connection: Connection) -> None:
    SecurityBase.metadata.create_all(bind=connection, checkfirst=True)


def _credential_references_v1(connection: Connection) -> None:
    cast(Table, CredencialReferenciaORM.__table__).create(
        bind=connection, checkfirst=True
    )


def _legacy_app_schema_v1(connection: Connection) -> None:
    legacy_metadata.create_all(bind=connection, checkfirst=True)


def _orders_authoritative_v1(connection: Connection) -> None:
    OrdersBase.metadata.create_all(bind=connection, checkfirst=True)


def _payments_authoritative_v1(connection: Connection) -> None:
    PaymentsBase.metadata.create_all(bind=connection, checkfirst=True)


def _stock_authoritative_v1(connection: Connection) -> None:
    StockBase.metadata.create_all(bind=connection, checkfirst=True)


def _event_bus_persistence_v1(connection: Connection) -> None:
    EventBusBase.metadata.create_all(bind=connection, checkfirst=True)


def _audit_log_v1(connection: Connection) -> None:
    cast(Table, EventoAuditoriaORM.__table__).create(bind=connection, checkfirst=True)


def _pdv_authoritative_runtime_v1(connection: Connection) -> None:
    PDVBase.metadata.create_all(bind=connection, checkfirst=True)


def _kds_authoritative_runtime_v1(connection: Connection) -> None:
    KDSBase.metadata.create_all(bind=connection, checkfirst=True)


def _external_services_config_v1(connection: Connection) -> None:
    IntegrationConfigBase.metadata.create_all(bind=connection, checkfirst=True)


def _revert_external_services_config_v1(connection: Connection) -> None:
    IntegrationConfigBase.metadata.drop_all(bind=connection, checkfirst=True)


def _restaurant_operations_runtime_v1(connection: Connection) -> None:
    SalaoBase.metadata.create_all(bind=connection, checkfirst=True)
    DeliveryBase.metadata.create_all(bind=connection, checkfirst=True)
    ImpressaoBase.metadata.create_all(bind=connection, checkfirst=True)


def _revert_restaurant_operations_runtime_v1(connection: Connection) -> None:
    ImpressaoBase.metadata.drop_all(bind=connection, checkfirst=True)
    DeliveryBase.metadata.drop_all(bind=connection, checkfirst=True)
    SalaoBase.metadata.drop_all(bind=connection, checkfirst=True)


def _core_runtime_v1(connection: Connection) -> None:
    CoreRuntimeBase.metadata.create_all(bind=connection, checkfirst=True)


def _revert_core_runtime_v1(connection: Connection) -> None:
    CoreRuntimeBase.metadata.drop_all(bind=connection, checkfirst=True)


DEFAULT_MIGRATIONS: tuple[Migration, ...] = (
    Migration("0001_security_identity_v1", _security_identity_v1),
    Migration("0002_credential_references_v1", _credential_references_v1),
    Migration("0003_legacy_app_schema_v1", _legacy_app_schema_v1),
    Migration("0004_orders_authoritative_v1", _orders_authoritative_v1),
    Migration("0005_payments_authoritative_v1", _payments_authoritative_v1),
    Migration("0006_stock_authoritative_v1", _stock_authoritative_v1),
    Migration("0007_event_bus_persistence_v1", _event_bus_persistence_v1),
    Migration("0008_audit_log_v1", _audit_log_v1),
    Migration("0009_pdv_authoritative_runtime_v1", _pdv_authoritative_runtime_v1),
    Migration("0010_kds_authoritative_runtime_v1", _kds_authoritative_runtime_v1),
    Migration(
        "0011_external_services_config_v1",
        _external_services_config_v1,
        _revert_external_services_config_v1,
    ),
    Migration(
        "0012_restaurant_operations_runtime_v1",
        _restaurant_operations_runtime_v1,
        _revert_restaurant_operations_runtime_v1,
    ),
    Migration("0013_core_runtime_v1", _core_runtime_v1, _revert_core_runtime_v1),
    Migration("0014_legacy_schema_upgrade_v1", upgrade_legacy_schema_v1),
    Migration("0015_legacy_schema_reconciliation_v1", reconcile_legacy_schema_v1),
    Migration("0016_integration_secret_vault_v1", upgrade_integration_secret_vault_v1),
    Migration("0017_admin_pin_v1", upgrade_admin_pin_v1),
    Migration("0018_admin_access_authorization_v1", upgrade_admin_access_authorization_v1),
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


def rollback_migration(engine: Engine, version: str) -> str:
    """Reverte uma migration explicitamente reversível em uma única transação.

    O rollback é deliberadamente restrito à última versão aplicada. Isso impede
    remover uma dependência estrutural ainda usada por migrations posteriores.
    Migrations sem ``revert`` permanecem fail-closed e exigem um plano manual.
    """

    by_version = {migration.version: migration for migration in DEFAULT_MIGRATIONS}
    migration = by_version.get(version)
    if migration is None:
        raise ValueError("migration desconhecida")
    if migration.revert is None:
        raise RuntimeError("migration nao possui rollback automatico")

    with engine.begin() as connection:
        applied = applied_versions(connection)
        if version not in applied:
            raise RuntimeError("migration nao aplicada")
        latest = next(
            (
                candidate.version
                for candidate in reversed(DEFAULT_MIGRATIONS)
                if candidate.version in applied
            ),
            None,
        )
        if latest != version:
            raise RuntimeError("rollback permitido somente para a ultima migration")
        migration.revert(connection)
        connection.execute(
            delete(_schema_migrations).where(_schema_migrations.c.version == version)
        )
    return version
