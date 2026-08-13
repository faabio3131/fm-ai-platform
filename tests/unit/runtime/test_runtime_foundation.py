from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect

from core.runtime.backup import (
    BackupRetentionPolicy,
    backup_database,
    prune_backups,
    restore_database,
    verify_backup,
)
from core.runtime.config import RuntimeEnvironment, load_runtime_settings
from core.runtime.database import build_engine, check_database_health
from core.runtime.registry import ModuleSpec, module_readiness
from migrations.runner import assert_schema_current, pending_versions, run_migrations

_EXPECTED_MIGRATIONS = (
    "0001_security_identity_v1",
    "0002_credential_references_v1",
    "0003_legacy_app_schema_v1",
    "0004_orders_authoritative_v1",
    "0005_payments_authoritative_v1",
    "0006_stock_authoritative_v1",
    "0007_event_bus_persistence_v1",
)


def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "FM_AI_TEST_MODE",
        "FM_AI_ENV",
        "DATABASE_URL",
        "FM_AI_TENANT_ID",
        "FM_AI_UNIDADE_ID",
        "FM_AI_ALLOW_SQLITE_COMMERCIAL",
        "FM_AI_SAMPLE_V1",
        "FM_AI_ADAPTER_ORDERS",
        "FM_AI_ADAPTER_AUTH",
    ):
        monkeypatch.delenv(name, raising=False)


def test_development_keeps_local_sqlite_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)
    settings = load_runtime_settings()
    assert settings.environment is RuntimeEnvironment.DEVELOPMENT
    assert settings.database_url == "sqlite:///./banco_erp_local.db"


def test_production_requires_explicit_database(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_ENV", "production")
    monkeypatch.setenv("FM_AI_TENANT_ID", "tenant-a")
    monkeypatch.setenv("FM_AI_UNIDADE_ID", "loja-1")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        load_runtime_settings()


def test_production_requires_explicit_tenant_and_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:secret@db.internal/gerente_ai"
    )
    with pytest.raises(RuntimeError, match="FM_AI_TENANT_ID"):
        load_runtime_settings()


def test_production_rejects_sqlite_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_ENV", "production")
    monkeypatch.setenv("FM_AI_TENANT_ID", "tenant-a")
    monkeypatch.setenv("FM_AI_UNIDADE_ID", "loja-1")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./nao-usar.db")
    with pytest.raises(RuntimeError, match="SQLite"):
        load_runtime_settings()


def test_production_accepts_server_database_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_ENV", "production")
    monkeypatch.setenv("FM_AI_TENANT_ID", "tenant-a")
    monkeypatch.setenv("FM_AI_UNIDADE_ID", "loja-1")
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://user:secret@db.internal/gerente_ai"
    )
    settings = load_runtime_settings()
    assert settings.commercial is True
    assert settings.tenant_id == "tenant-a"


def test_registry_preserves_e2e_flag_without_real_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_SAMPLE_V1", "1")
    status = module_readiness(
        ModuleSpec("sample", "FM_AI_SAMPLE_V1", ("orders", "auth"))
    )
    assert status.enabled is True
    assert status.test_mode is True
    assert status.missing_adapters == ()


def test_registry_blocks_normal_runtime_until_all_adapters_are_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_SAMPLE_V1", "1")
    monkeypatch.setenv("FM_AI_ADAPTER_ORDERS", "sqlalchemy")
    status = module_readiness(
        ModuleSpec("sample", "FM_AI_SAMPLE_V1", ("orders", "auth"))
    )
    assert status.enabled is False
    assert status.missing_adapters == ("auth",)

    monkeypatch.setenv("FM_AI_ADAPTER_AUTH", "production")
    status = module_readiness(
        ModuleSpec("sample", "FM_AI_SAMPLE_V1", ("orders", "auth"))
    )
    assert status.enabled is True
    assert status.missing_adapters == ()


def test_sqlite_health_and_versioned_migration_are_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    settings = load_runtime_settings(test_database_url="sqlite:///:memory:")
    engine = build_engine(settings)
    assert check_database_health(engine).ok is True
    assert pending_versions(engine) == _EXPECTED_MIGRATIONS
    with pytest.raises(RuntimeError, match="Schema comercial desatualizado"):
        assert_schema_current(engine)

    assert run_migrations(engine) == _EXPECTED_MIGRATIONS
    assert run_migrations(engine) == ()
    assert pending_versions(engine) == ()
    assert_schema_current(engine)

    tables = set(inspect(engine).get_table_names())
    for table in (
        "fm_schema_migrations",
        "fm_usuarios_v1",
        "fm_usuario_papeis_v1",
        "fm_credenciais_referencias_v1",
        "produtos",
        "vendas",
        "configuracoes_meta",
        "pedidos_v1",
        "obrigacoes_pagamento_v1",
        "estoque_ledger_v1",
        "event_outbox_v1",
        "event_inbox_v1",
        "event_dlq_v1",
    ):
        assert table in tables


def _create_source_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE teste (id INTEGER PRIMARY KEY, valor TEXT NOT NULL)")
    connection.execute("INSERT INTO teste(valor) VALUES ('ok')")
    connection.commit()
    connection.close()


def test_sqlite_backup_manifest_and_restore(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    _create_source_database(source)

    manifest = backup_database(f"sqlite:///{source}", backup)
    assert manifest.size_bytes > 0
    assert verify_backup(backup).sha256 == manifest.sha256

    restore_database(
        f"sqlite:///{restored}",
        backup,
        confirm_database=str(restored),
    )
    restored_connection = sqlite3.connect(restored)
    try:
        value = restored_connection.execute("SELECT valor FROM teste").fetchone()
    finally:
        restored_connection.close()
    assert value == ("ok",)


def test_retention_keeps_recent_and_last_backup_but_prunes_old_excess(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    _create_source_database(source)
    backups: list[Path] = []
    now = datetime(2026, 8, 12, 20, 0, tzinfo=timezone.utc)

    for index, age_days in enumerate((0, 10, 20), start=1):
        path = tmp_path / f"backup-{index}.sqlite3"
        backup_database(f"sqlite:///{source}", path)
        manifest_path = path.with_suffix(path.suffix + ".manifest.json")
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["created_at"] = (now - timedelta(days=age_days)).isoformat()
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        backups.append(path)

    removed = prune_backups(
        tmp_path,
        BackupRetentionPolicy(keep_last=1, max_age_days=5),
        now=now,
    )
    assert set(removed) == {backups[1], backups[2]}
    assert backups[0].exists()
    assert not backups[1].exists()
    assert not backups[2].exists()
