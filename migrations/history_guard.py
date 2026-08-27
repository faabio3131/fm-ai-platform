"""Guardas fail-closed do histórico de migrations e do schema congelado."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, inspect, text
from sqlalchemy.engine import Connection

from migrations.manifest import MANIFEST_PATH, load_manifest

MIGRATION_TABLE = "fm_schema_migrations"
CHECKSUM_COLUMN = "migration_sha256"
INTEGRITY_VERSION = "0030_migration_history_integrity_v1"
HISTORY_BASELINE_PATH = Path(__file__).with_name("history_baseline_v1.json")
SCHEMA_BASELINE_PATH = Path(__file__).with_name("schema_baseline_v1.json")
SCHEMA_ALGORITHM = "sha256:normalized-schema-signature-v1"
REPO_ROOT = Path(__file__).resolve().parents[1]


class MigrationHistoryError(RuntimeError):
    """O ledger aplicado divergiu da sequência histórica aprovada."""


class MigrationHistoryBaselineError(RuntimeError):
    """O source histórico divergiu do baseline aprovado."""


class SchemaBaselineError(RuntimeError):
    """O schema materializado divergiu do baseline arquitetural."""


@dataclass(frozen=True)
class AppliedMigrationRecord:
    version: str
    checksum: str | None


def applied_history(connection: Connection) -> tuple[AppliedMigrationRecord, ...]:
    inspector = inspect(connection)
    if MIGRATION_TABLE not in inspector.get_table_names():
        return ()

    columns = {str(column["name"]) for column in inspector.get_columns(MIGRATION_TABLE)}
    if CHECKSUM_COLUMN in columns:
        rows = connection.execute(
            text(
                "SELECT version, migration_sha256 "
                "FROM fm_schema_migrations ORDER BY applied_at, version"
            )
        ).all()
        return tuple(
            AppliedMigrationRecord(
                version=str(row.version),
                checksum=None if row.migration_sha256 is None else str(row.migration_sha256),
            )
            for row in rows
        )

    versions = connection.execute(
        text("SELECT version FROM fm_schema_migrations ORDER BY applied_at, version")
    ).scalars()
    return tuple(
        AppliedMigrationRecord(version=str(version), checksum=None)
        for version in versions
    )


def assert_applied_history(
    connection: Connection,
    official_versions: tuple[str, ...],
) -> tuple[AppliedMigrationRecord, ...]:
    records = applied_history(connection)
    versions = tuple(record.version for record in records)

    if len(versions) != len(set(versions)):
        raise MigrationHistoryError("historico aplicado contem versao duplicada")

    official_set = set(official_versions)
    unknown = sorted(set(versions) - official_set)
    if unknown:
        raise MigrationHistoryError(
            "historico aplicado contem versao desconhecida: " + ", ".join(unknown)
        )

    applied_set = set(versions)
    expected_prefix = set(official_versions[: len(applied_set)])
    if applied_set != expected_prefix:
        missing = sorted(expected_prefix - applied_set)
        late = sorted(applied_set - expected_prefix)
        details: list[str] = []
        if missing:
            details.append("faltantes=" + ",".join(missing))
        if late:
            details.append("fora_de_ordem=" + ",".join(late))
        raise MigrationHistoryError(
            "historico aplicado nao forma prefixo oficial"
            + ("; " + "; ".join(details) if details else "")
        )

    manifest = {item.version: item.sha256 for item in load_manifest()}
    integrity_applied = INTEGRITY_VERSION in applied_set
    columns = {
        str(column["name"])
        for column in inspect(connection).get_columns(MIGRATION_TABLE)
    }
    if integrity_applied and CHECKSUM_COLUMN not in columns:
        raise MigrationHistoryError(
            "migration de integridade aplicada sem coluna de checksum no ledger"
        )

    for record in records:
        expected = manifest.get(record.version)
        if expected is None:
            raise MigrationHistoryError(
                f"manifest nao cobre migration aplicada {record.version}"
            )
        if record.checksum is None:
            if integrity_applied:
                raise MigrationHistoryError(
                    f"checksum historico ausente para {record.version}"
                )
            continue
        if record.checksum != expected:
            raise MigrationHistoryError(
                f"checksum historico divergente para {record.version}"
            )

    return records


def _load_history_baseline(
    path: Path = HISTORY_BASELINE_PATH,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format_version") != 1:
        raise MigrationHistoryBaselineError("formato do baseline historico divergente")
    return payload


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def assert_frozen_history(
    *,
    root: Path = REPO_ROOT,
    baseline_path: Path = HISTORY_BASELINE_PATH,
    manifest_path: Path = MANIFEST_PATH,
) -> None:
    baseline = _load_history_baseline(baseline_path)
    manifest = load_manifest(manifest_path)

    frozen_entries = tuple(
        (str(item["version"]), str(item["sha256"]))
        for item in baseline.get("manifest_entries", [])
    )
    current_entries = tuple(
        (item.version, item.sha256)
        for item in manifest[: len(frozen_entries)]
    )
    if current_entries != frozen_entries:
        raise MigrationHistoryBaselineError(
            "fingerprint historico alterado ou reordenado"
        )
    if not frozen_entries:
        raise MigrationHistoryBaselineError("baseline historico vazio")
    if frozen_entries[-1][0] != baseline.get("frozen_through"):
        raise MigrationHistoryBaselineError(
            "frozen_through diverge da ultima migration congelada"
        )

    frozen_versions = {version for version, _ in frozen_entries}
    seen_modules: set[str] = set()
    for item in baseline.get("module_blobs", []):
        version = str(item["version"])
        relative = Path(str(item["path"]))
        expected = str(item["git_blob_sha"])
        if version not in frozen_versions:
            raise MigrationHistoryBaselineError(
                f"modulo congelado sem versao historica: {version}"
            )
        if version in seen_modules:
            raise MigrationHistoryBaselineError(
                f"modulo historico duplicado para {version}"
            )
        seen_modules.add(version)
        if _git_blob_sha(root / relative) != expected:
            raise MigrationHistoryBaselineError(
                f"source historico alterado: {version} ({relative.as_posix()})"
            )


def load_history_baseline() -> dict[str, Any]:
    return _load_history_baseline()


def _normalize_default(value: object, *, primary_key: bool) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    if primary_key and "nextval(" in normalized.lower():
        return None
    return normalized


def schema_signature(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    tables: dict[str, Any] = {}

    for table in sorted(
        name for name in inspector.get_table_names() if name != "sqlite_sequence"
    ):
        primary_key = tuple(
            str(column)
            for column in inspector.get_pk_constraint(table).get(
                "constrained_columns"
            )
            or ()
        )
        pk_set = set(primary_key)
        tables[table] = {
            "columns": tuple(
                (
                    str(column["name"]),
                    str(column["type"]).upper(),
                    bool(column["nullable"]),
                    _normalize_default(
                        column.get("default"),
                        primary_key=str(column["name"]) in pk_set,
                    ),
                )
                for column in inspector.get_columns(table)
            ),
            "primary_key": primary_key,
            "uniques": tuple(
                sorted(
                    (
                        str(item.get("name") or ""),
                        tuple(str(c) for c in item.get("column_names") or ()),
                    )
                    for item in inspector.get_unique_constraints(table)
                )
            ),
            "indexes": tuple(
                sorted(
                    (
                        str(item.get("name") or ""),
                        tuple(str(c) for c in item.get("column_names") or ()),
                        bool(item.get("unique")),
                    )
                    for item in inspector.get_indexes(table)
                )
            ),
            "foreign_keys": tuple(
                sorted(
                    (
                        tuple(str(c) for c in item.get("constrained_columns") or ()),
                        str(item.get("referred_schema") or ""),
                        str(item.get("referred_table") or ""),
                        tuple(str(c) for c in item.get("referred_columns") or ()),
                    )
                    for item in inspector.get_foreign_keys(table)
                )
            ),
            "checks": tuple(
                sorted(
                    (
                        str(item.get("name") or ""),
                        " ".join(str(item.get("sqltext") or "").split()),
                    )
                    for item in inspector.get_check_constraints(table)
                )
            ),
        }

    return {
        "algorithm": SCHEMA_ALGORITHM,
        "dialect": engine.dialect.name,
        "tables": tables,
    }


def schema_digest(engine: Engine) -> tuple[str, int]:
    signature = schema_signature(engine)
    encoded = json.dumps(
        signature,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest(), len(signature["tables"])


def assert_schema_baseline(
    engine: Engine,
    *,
    baseline_path: Path = SCHEMA_BASELINE_PATH,
) -> None:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline.get("algorithm") != SCHEMA_ALGORITHM:
        raise SchemaBaselineError("algoritmo do schema baseline divergente")
    if baseline.get("dialect") != engine.dialect.name:
        raise SchemaBaselineError("dialeto do schema baseline divergente")

    digest, table_count = schema_digest(engine)
    expected = str(baseline.get("signature_sha256") or "")
    if expected == "PENDING":
        raise SchemaBaselineError(
            f"schema baseline pendente: sha256={digest}; table_count={table_count}"
        )
    if digest != expected:
        raise SchemaBaselineError(
            f"schema final divergiu do baseline: esperado={expected}; atual={digest}"
        )
    if int(baseline.get("table_count", -1)) != table_count:
        raise SchemaBaselineError(
            "quantidade de tabelas divergiu do schema baseline"
        )
