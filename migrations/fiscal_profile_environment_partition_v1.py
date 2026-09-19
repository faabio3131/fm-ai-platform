"""Migration 0044 — harden fiscal profile partitioning by environment."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    inspect,
    insert,
    text,
)
from sqlalchemy.engine import Connection

_ISSUER_TABLE = "fiscal_issuer_profiles_v1"
_PRODUCT_TABLE = "fiscal_product_bindings_v1"
_VALID_ENVIRONMENTS = frozenset({"homologation", "production"})
_ISSUER_PK = ("tenant_id", "unit_id", "environment", "profile_version")
_PRODUCT_PK = (
    "tenant_id",
    "unit_id",
    "environment",
    "product_id",
    "profile_version",
)


def _primary_key(connection: Connection, table: str) -> tuple[str, ...]:
    constrained = inspect(connection).get_pk_constraint(table).get(
        "constrained_columns"
    )
    return tuple(str(column) for column in constrained or ())


def _columns(connection: Connection, table: str) -> frozenset[str]:
    return frozenset(
        str(column["name"]) for column in inspect(connection).get_columns(table)
    )


def _decoded_payload(raw: str, *, table: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{table} contains invalid fiscal profile JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{table} fiscal profile payload must be an object")
    return payload


def _payload_scope(
    raw: str,
    *,
    table: str,
    tenant_id: str,
    unit_id: str,
) -> tuple[dict[str, Any], str]:
    payload = _decoded_payload(raw, table=table)
    scope = payload.get("scope")
    if not isinstance(scope, dict):
        raise RuntimeError(f"{table} fiscal profile payload is missing scope")
    if str(scope.get("tenant_id") or "") != tenant_id:
        raise RuntimeError(f"{table} payload tenant differs from persisted tenant")
    if str(scope.get("unit_id") or "") != unit_id:
        raise RuntimeError(f"{table} payload unit differs from persisted unit")
    environment = str(scope.get("environment") or "")
    if environment not in _VALID_ENVIRONMENTS:
        raise RuntimeError(f"{table} payload contains invalid fiscal environment")
    return payload, environment


def _issuer_rows(connection: Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        text(
            "SELECT tenant_id, unit_id, profile_version, environment, payload_json, "
            "certificate_reference, provider_config_id, valid_from, valid_until "
            f"FROM {_ISSUER_TABLE}"
        )
    ).mappings()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        _, payload_environment = _payload_scope(
            str(item["payload_json"]),
            table=_ISSUER_TABLE,
            tenant_id=str(item["tenant_id"]),
            unit_id=str(item["unit_id"]),
        )
        persisted_environment = str(item["environment"])
        if persisted_environment not in _VALID_ENVIRONMENTS:
            raise RuntimeError(
                f"{_ISSUER_TABLE} contains invalid persisted fiscal environment"
            )
        if payload_environment != persisted_environment:
            raise RuntimeError(
                f"{_ISSUER_TABLE} payload environment differs from persisted environment"
            )
        result.append(item)
    return result


def _product_rows(connection: Connection) -> list[dict[str, Any]]:
    has_environment = "environment" in _columns(connection, _PRODUCT_TABLE)
    environment_column = "environment, " if has_environment else ""
    rows = connection.execute(
        text(
            "SELECT tenant_id, unit_id, "
            f"{environment_column}"
            "product_id, profile_version, payload_json, "
            f"valid_from, valid_until FROM {_PRODUCT_TABLE}"
        )
    ).mappings()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        payload, environment = _payload_scope(
            str(item["payload_json"]),
            table=_PRODUCT_TABLE,
            tenant_id=str(item["tenant_id"]),
            unit_id=str(item["unit_id"]),
        )
        if str(payload.get("product_id") or "") != str(item["product_id"]):
            raise RuntimeError(
                f"{_PRODUCT_TABLE} payload product differs from persisted product"
            )
        if has_environment and str(item["environment"]) != environment:
            raise RuntimeError(
                f"{_PRODUCT_TABLE} payload environment differs from persisted environment"
            )
        item["environment"] = environment
        result.append(item)
    return result


def _issuer_rebuild_table(name: str) -> Table:
    metadata = MetaData()
    return Table(
        name,
        metadata,
        Column("tenant_id", String(128), nullable=False),
        Column("unit_id", String(128), nullable=False),
        Column("environment", String(32), nullable=False),
        Column("profile_version", Integer, nullable=False),
        Column("payload_json", Text, nullable=False),
        Column("certificate_reference", String(256)),
        Column("provider_config_id", String(256)),
        Column("valid_from", DateTime(timezone=True), nullable=False),
        Column("valid_until", DateTime(timezone=True)),
        PrimaryKeyConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "profile_version",
        ),
    )


def _product_rebuild_table(name: str) -> Table:
    metadata = MetaData()
    return Table(
        name,
        metadata,
        Column("tenant_id", String(128), nullable=False),
        Column("unit_id", String(128), nullable=False),
        Column("environment", String(32), nullable=False),
        Column("product_id", String(128), nullable=False),
        Column("profile_version", Integer, nullable=False),
        Column("payload_json", Text, nullable=False),
        Column("valid_from", DateTime(timezone=True), nullable=False),
        Column("valid_until", DateTime(timezone=True)),
        PrimaryKeyConstraint(
            "tenant_id",
            "unit_id",
            "environment",
            "product_id",
            "profile_version",
        ),
    )


def _replace_table(
    connection: Connection,
    *,
    source: str,
    temporary: str,
    rebuilt: Table,
    rows: list[dict[str, Any]],
) -> None:
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {temporary}")
    rebuilt.create(bind=connection)
    if rows:
        connection.execute(insert(rebuilt), rows)
    connection.exec_driver_sql(f"DROP TABLE {source}")
    connection.exec_driver_sql(f"ALTER TABLE {temporary} RENAME TO {source}")


def _rebuild_issuer(connection: Connection, rows: list[dict[str, Any]]) -> None:
    temporary = f"{_ISSUER_TABLE}__wp031_pre_e"
    _replace_table(
        connection,
        source=_ISSUER_TABLE,
        temporary=temporary,
        rebuilt=_issuer_rebuild_table(temporary),
        rows=rows,
    )


def _rebuild_product(connection: Connection, rows: list[dict[str, Any]]) -> None:
    temporary = f"{_PRODUCT_TABLE}__wp031_pre_e"
    _replace_table(
        connection,
        source=_PRODUCT_TABLE,
        temporary=temporary,
        rebuilt=_product_rebuild_table(temporary),
        rows=rows,
    )


def upgrade_fiscal_profile_environment_partition_v1(
    connection: Connection,
) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    if _ISSUER_TABLE not in tables or _PRODUCT_TABLE not in tables:
        raise RuntimeError(
            "fiscal profile tables must exist before environment partition hardening"
        )

    issuer_rows = _issuer_rows(connection)
    product_rows = _product_rows(connection)

    issuer_correct = (
        "environment" in _columns(connection, _ISSUER_TABLE)
        and _primary_key(connection, _ISSUER_TABLE) == _ISSUER_PK
    )
    product_correct = (
        "environment" in _columns(connection, _PRODUCT_TABLE)
        and _primary_key(connection, _PRODUCT_TABLE) == _PRODUCT_PK
    )

    if not issuer_correct:
        _rebuild_issuer(connection, issuer_rows)
    if not product_correct:
        _rebuild_product(connection, product_rows)

    if _primary_key(connection, _ISSUER_TABLE) != _ISSUER_PK:
        raise RuntimeError("issuer fiscal profile primary key hardening failed")
    if _primary_key(connection, _PRODUCT_TABLE) != _PRODUCT_PK:
        raise RuntimeError("product fiscal profile primary key hardening failed")
