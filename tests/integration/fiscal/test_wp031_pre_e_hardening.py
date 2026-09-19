from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateTable

from infra.fiscal.modelos_orm import FiscalBase
from infra.fiscal.repositorios_sqlalchemy import FiscalOutboxStoreSQLAlchemy
from kordena_fiscal.contingency import (
    FiscalOutboxService,
    InMemoryFiscalOutboxStore,
    OutboxStateError,
)
from kordena_fiscal.domain import (
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from migrations.fiscal_profile_environment_partition_v1 import (
    _issuer_rebuild_table,
    _product_rebuild_table,
    upgrade_fiscal_profile_environment_partition_v1,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=timezone.utc)

def _scope() -> ExecutionScope:
    return ExecutionScope(
        tenant_id="tenant-a",
        unit_id="unit-a",
        environment=FiscalEnvironment.HOMOLOGATION,
        correlation_id="corr-pre-e",
    )


def _memory_store() -> InMemoryFiscalOutboxStore:
    return InMemoryFiscalOutboxStore()


def _sql_store() -> FiscalOutboxStoreSQLAlchemy:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    return FiscalOutboxStoreSQLAlchemy(
        sessionmaker(engine, expire_on_commit=False)
    )


@pytest.fixture(params=[_memory_store, _sql_store], ids=["memory", "sqlalchemy"])
def outbox_store(request):
    return request.param()


def _queued(store):
    result = FiscalOutboxService(store).enqueue(
        scope=_scope(),
        operation="nfce.issue",
        deduplication_key="sale-1",
        payload=b'{"sale":"1"}',
        created_at=NOW,
    )
    return result.entry


@pytest.mark.parametrize("invalid_limit", [True, False, 1.5, "1", None, 0, -1])
def test_pre_e_outbox_claim_due_contract_rejects_invalid_limits(
    outbox_store,
    invalid_limit,
) -> None:
    _queued(outbox_store)
    with pytest.raises(FiscalValidationError, match="positive integer"):
        outbox_store.claim_due(
            now=NOW,
            limit=invalid_limit,
            lease_duration=timedelta(seconds=30),
        )


def test_pre_e_outbox_claim_due_accepts_positive_integer(outbox_store) -> None:
    queued = _queued(outbox_store)
    claimed = outbox_store.claim_due(
        now=NOW,
        limit=1,
        lease_duration=timedelta(seconds=30),
    )
    assert len(claimed) == 1
    assert claimed[0].entry_id == queued.entry_id
    assert claimed[0].attempt_count == 1


def test_pre_e_outbox_reschedule_requires_timezone_aware_datetime(
    outbox_store,
) -> None:
    _queued(outbox_store)
    claimed = outbox_store.claim_due(
        now=NOW,
        limit=1,
        lease_duration=timedelta(seconds=30),
    )[0]
    naive = NOW.replace(tzinfo=None)
    with pytest.raises(FiscalValidationError, match="timezone-aware"):
        outbox_store.reschedule(
            claimed.entry_id,
            expected_attempt=1,
            available_at=naive,
            error="temporary",
        )

    available_at = NOW + timedelta(minutes=5)
    retried = outbox_store.reschedule(
        claimed.entry_id,
        expected_attempt=1,
        available_at=available_at,
        error="temporary",
    )
    assert retried.available_at == available_at
    assert retried.last_error == "temporary"


def test_pre_e_outbox_get_validates_entry_identity(outbox_store) -> None:
    with pytest.raises(FiscalValidationError):
        outbox_store.get("not-a-sha256")


def test_pre_e_outbox_transition_order_matches_reference_store(outbox_store) -> None:
    missing = "0" * 64
    with pytest.raises(OutboxStateError, match="does not exist"):
        outbox_store.mark_succeeded(
            missing,
            expected_attempt=1,
            completion_reference="",
        )
    with pytest.raises(OutboxStateError, match="does not exist"):
        outbox_store.dead_letter(
            missing,
            expected_attempt=1,
            error="",
        )


def _create_previous_profile_schema(connection) -> None:
    connection.exec_driver_sql(
        """
        CREATE TABLE fiscal_issuer_profiles_v1 (
            tenant_id VARCHAR(128) NOT NULL,
            unit_id VARCHAR(128) NOT NULL,
            profile_version INTEGER NOT NULL,
            environment VARCHAR(32) NOT NULL,
            payload_json TEXT NOT NULL,
            certificate_reference VARCHAR(256),
            provider_config_id VARCHAR(256),
            valid_from TIMESTAMP NOT NULL,
            valid_until TIMESTAMP,
            PRIMARY KEY (tenant_id, unit_id, profile_version)
        )
        """
    )
    connection.exec_driver_sql(
        """
        CREATE TABLE fiscal_product_bindings_v1 (
            tenant_id VARCHAR(128) NOT NULL,
            unit_id VARCHAR(128) NOT NULL,
            product_id VARCHAR(128) NOT NULL,
            profile_version INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            valid_from TIMESTAMP NOT NULL,
            valid_until TIMESTAMP,
            PRIMARY KEY (tenant_id, unit_id, product_id, profile_version)
        )
        """
    )


def _profile_payload(*, environment: str, product_id: str | None = None) -> str:
    payload: dict[str, object] = {
        "scope": {
            "tenant_id": "tenant-a",
            "unit_id": "unit-a",
            "environment": environment,
            "correlation_id": "corr-old",
        }
    }
    if product_id is not None:
        payload["product_id"] = product_id
    return json.dumps(payload, sort_keys=True)


def test_pre_e_migration_upgrades_previous_schema_and_preserves_data() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_previous_profile_schema(connection)
        connection.execute(
            text(
                "INSERT INTO fiscal_issuer_profiles_v1 "
                "(tenant_id, unit_id, profile_version, environment, payload_json, "
                "certificate_reference, provider_config_id, valid_from, valid_until) "
                "VALUES (:tenant, :unit, 1, :environment, :payload, :certificate, "
                ":provider, :valid_from, NULL)"
            ),
            {
                "tenant": "tenant-a",
                "unit": "unit-a",
                "environment": "homologation",
                "payload": _profile_payload(environment="homologation"),
                "certificate": "vault://fiscal/cert-a",
                "provider": "integration:fiscal:a",
                "valid_from": NOW,
            },
        )
        connection.execute(
            text(
                "INSERT INTO fiscal_product_bindings_v1 "
                "(tenant_id, unit_id, product_id, profile_version, payload_json, "
                "valid_from, valid_until) "
                "VALUES (:tenant, :unit, :product, 1, :payload, :valid_from, NULL)"
            ),
            {
                "tenant": "tenant-a",
                "unit": "unit-a",
                "product": "42",
                "payload": _profile_payload(
                    environment="homologation",
                    product_id="42",
                ),
                "valid_from": NOW,
            },
        )
        upgrade_fiscal_profile_environment_partition_v1(connection)

    inspector = inspect(engine)
    assert tuple(
        inspector.get_pk_constraint("fiscal_issuer_profiles_v1")[
            "constrained_columns"
        ]
    ) == ("tenant_id", "unit_id", "environment", "profile_version")
    assert tuple(
        inspector.get_pk_constraint("fiscal_product_bindings_v1")[
            "constrained_columns"
        ]
    ) == (
        "tenant_id",
        "unit_id",
        "environment",
        "product_id",
        "profile_version",
    )
    with engine.connect() as connection:
        issuer = connection.execute(
            text(
                "SELECT environment, certificate_reference "
                "FROM fiscal_issuer_profiles_v1"
            )
        ).one()
        product = connection.execute(
            text(
                "SELECT environment, product_id "
                "FROM fiscal_product_bindings_v1"
            )
        ).one()
    assert tuple(issuer) == ("homologation", "vault://fiscal/cert-a")
    assert tuple(product) == ("homologation", "42")


def test_pre_e_migration_is_idempotent_on_fresh_current_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    with engine.begin() as connection:
        upgrade_fiscal_profile_environment_partition_v1(connection)
    inspector = inspect(engine)
    assert "environment" in {
        str(column["name"])
        for column in inspector.get_columns("fiscal_product_bindings_v1")
    }


def test_pre_e_migration_fails_closed_on_payload_environment_mismatch() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_previous_profile_schema(connection)
        connection.execute(
            text(
                "INSERT INTO fiscal_issuer_profiles_v1 "
                "(tenant_id, unit_id, profile_version, environment, payload_json, "
                "valid_from, valid_until) "
                "VALUES ('tenant-a', 'unit-a', 1, 'homologation', :payload, "
                ":valid_from, NULL)"
            ),
            {
                "payload": _profile_payload(environment="production"),
                "valid_from": NOW,
            },
        )
        with pytest.raises(RuntimeError, match="payload environment differs"):
            upgrade_fiscal_profile_environment_partition_v1(connection)

def _table_shape(engine, table: str) -> tuple[tuple[object, ...], tuple[str, ...]]:
    inspector = inspect(engine)
    columns = tuple(
        (
            str(column["name"]),
            str(column["type"]).upper(),
            bool(column["nullable"]),
        )
        for column in inspector.get_columns(table)
    )
    primary_key = tuple(
        str(column)
        for column in inspector.get_pk_constraint(table)["constrained_columns"]
    )
    return columns, primary_key


def test_pre_e_migration_upgrade_matches_fresh_profile_schema_shape() -> None:
    upgraded = create_engine("sqlite+pysqlite:///:memory:")
    with upgraded.begin() as connection:
        _create_previous_profile_schema(connection)
        upgrade_fiscal_profile_environment_partition_v1(connection)

    fresh = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(fresh)

    for table in (
        "fiscal_issuer_profiles_v1",
        "fiscal_product_bindings_v1",
    ):
        assert _table_shape(upgraded, table) == _table_shape(fresh, table)

def test_pre_e_migration_preserves_timezone_types_for_postgresql() -> None:
    dialect = postgresql.dialect()
    issuer_sql = str(
        CreateTable(_issuer_rebuild_table("issuer_tmp")).compile(dialect=dialect)
    ).upper()
    product_sql = str(
        CreateTable(_product_rebuild_table("product_tmp")).compile(dialect=dialect)
    ).upper()

    assert issuer_sql.count("TIMESTAMP WITH TIME ZONE") == 2
    assert product_sql.count("TIMESTAMP WITH TIME ZONE") == 2
