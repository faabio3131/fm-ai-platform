from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "e2e" / "test_database.py"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INIT_SCRIPT = PROJECT_ROOT / "tests" / "e2e" / "init_test_db.py"
FORBIDDEN_DB_PATH = Path(r"C:\fm-ai-platform\banco_erp_local.db")
SPEC = importlib.util.spec_from_file_location("e2e_test_database", MODULE_PATH)
assert SPEC and SPEC.loader
e2e_test_database = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e2e_test_database)


def _bootstrap_env(tmp_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "FM_AI_TEST_MODE": "1",
            "FM_AI_TEST_RESET_ON_START": "1",
            "FM_AI_TEST_TMPDIR": str(tmp_dir),
            "FM_AI_TEST_KEEP_TMP": "1",
        }
    )
    env.pop("FM_AI_KDS_V1", None)
    env.pop("PYTHONPATH", None)
    return env


def _assert_canonical_sandbox(db_path: Path) -> None:
    assert db_path.resolve() != (PROJECT_ROOT / "banco_erp_local.db").resolve()
    assert db_path.resolve() != FORBIDDEN_DB_PATH.resolve()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "select m.tenant_id, m.unidade_id, m.loja_id, m.ativo, l.nome_fantasia "
            "from fm_unidade_loja_legacy_v1 as m join lojas as l on l.id = m.loja_id"
        ).fetchall() == [
            ("tenant-local", "unidade-local", 1, 1, "Loja Sandbox")
        ]
        assert connection.execute(
            "select distinct cast(loja_id as integer) from produtos "
            "union select distinct cast(loja_id as integer) from insumos"
        ).fetchall() == [(1,)]
    finally:
        connection.close()


def test_bootstrap_entrypoint_matches_playwright_launcher(tmp_path):
    tmp_dir = tmp_path / "launcher-db"
    result = subprocess.run(
        [sys.executable, "tests/e2e/init_test_db.py"],
        cwd=PROJECT_ROOT,
        env=_bootstrap_env(tmp_dir),
        check=False,
        capture_output=True,
        text=True,
    )

    db_path = tmp_dir / "fm_ai_test.sqlite3"
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == db_path.resolve()
    assert db_path.is_relative_to(tmp_path)
    _assert_canonical_sandbox(db_path)


def test_bootstrap_entrypoint_absolute_path_is_independent_of_cwd(tmp_path):
    tmp_dir = tmp_path / "absolute-db"
    external_cwd = tmp_path / "outside-repository"
    external_cwd.mkdir()
    result = subprocess.run(
        [sys.executable, str(INIT_SCRIPT)],
        cwd=external_cwd,
        env=_bootstrap_env(tmp_dir),
        check=False,
        capture_output=True,
        text=True,
    )

    db_path = tmp_dir / "fm_ai_test.sqlite3"
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()).resolve() == db_path.resolve()
    assert db_path.is_relative_to(tmp_path)
    _assert_canonical_sandbox(db_path)


def test_reset_database_preserves_file_and_restores_seed(tmp_path, monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"
    loja_id = e2e_test_database.bootstrap_database(db_path)
    inode_before = db_path.stat().st_ino

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        cursor.execute("update produtos set nome = 'Alterado' where id = 1")
        cursor.execute(
            "insert into clientes (id, nome, whatsapp) values (99, 'Extra', '5500000000000')"
        )
        connection.commit()
    finally:
        cursor.close()
        connection.close()

    e2e_test_database.reset_database_in_place(db_path)

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        assert db_path.stat().st_ino == inode_before
        assert cursor.execute("select id, nome from produtos").fetchall() == [
            (1, "Burger Teste")
        ]
        assert cursor.execute("select id from clientes").fetchall() == [(1,)]
        assert cursor.execute(
            "select tenant_id, unidade_id, loja_id, ativo "
            "from fm_unidade_loja_legacy_v1"
        ).fetchall() == [("tenant-local", "unidade-local", loja_id, 1)]
        assert cursor.execute(
            "select distinct cast(loja_id as integer) from produtos "
            "union select distinct cast(loja_id as integer) from insumos"
        ).fetchall() == [(loja_id,)]
        assert cursor.execute("pragma foreign_key_check").fetchall() == []
    finally:
        cursor.close()
        connection.close()


def test_reset_database_retries_a_temporary_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"
    e2e_test_database.bootstrap_database(db_path)
    blocker = sqlite3.connect(db_path, check_same_thread=False)
    blocker.execute("begin exclusive")

    def release_lock():
        time.sleep(0.05)
        blocker.rollback()
        blocker.close()

    release_thread = threading.Thread(target=release_lock)
    release_thread.start()
    try:
        e2e_test_database.reset_database_in_place(db_path, attempts=3, retry_delay=0.1)
    finally:
        release_thread.join()

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        assert cursor.execute("select count(*) from produtos").fetchone() == (1,)
    finally:
        cursor.close()
        connection.close()


def test_kds_enabled_database_creates_and_preserves_canonical_schema(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    monkeypatch.setenv("FM_AI_KDS_V1", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"

    e2e_test_database.bootstrap_database(db_path)
    e2e_test_database.reset_database_in_place(db_path)

    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()
    try:
        existing = {
            row[0]
            for row in cursor.execute(
                "select name from sqlite_master where type='table'"
            )
        }
        assert e2e_test_database.KDS_CANONICAL_REQUIRED_TABLES <= existing
        assert cursor.execute("pragma foreign_key_check").fetchall() == []
    finally:
        cursor.close()
        connection.close()


def test_fresh_bootstrap_prepares_exact_mapping_before_server(tmp_path, monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"

    loja_id = e2e_test_database.bootstrap_database(db_path)

    connection = sqlite3.connect(db_path)
    try:
        assert loja_id == 1
        assert connection.execute(
            "select m.tenant_id, m.unidade_id, m.loja_id, m.ativo, l.nome_fantasia "
            "from fm_unidade_loja_legacy_v1 as m join lojas as l on l.id = m.loja_id"
        ).fetchall() == [
            ("tenant-local", "unidade-local", 1, 1, "Loja Sandbox")
        ]
        assert connection.execute(
            "select distinct cast(loja_id as integer) from produtos "
            "union select distinct cast(loja_id as integer) from insumos"
        ).fetchall() == [(1,)]
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            "delete from fm_unidade_loja_legacy_v1",
            "exatamente o mapping legado",
        ),
        (
            "update fm_unidade_loja_legacy_v1 set ativo = 0",
            "mapping ativo",
        ),
        (
            "update fm_unidade_loja_legacy_v1 set tenant_id = 'tenant-divergente'",
            "exatamente o mapping legado",
        ),
        (
            "update fm_unidade_loja_legacy_v1 set unidade_id = 'unidade-divergente'",
            "exatamente o mapping legado",
        ),
    ],
)
def test_reset_fails_closed_for_invalid_mapping(tmp_path, monkeypatch, mutation, message):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"
    e2e_test_database.bootstrap_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(mutation)
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match=message):
        e2e_test_database.reset_database_in_place(db_path)


def test_reset_fails_closed_for_ambiguous_mapping(tmp_path, monkeypatch):
    monkeypatch.setenv("FM_AI_TEST_MODE", "1")
    db_path = tmp_path / "fm_ai_test.sqlite3"
    e2e_test_database.bootstrap_database(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("insert into lojas (id, nome_fantasia) values (2, 'Outra Loja')")
        connection.execute(
            "insert into fm_unidade_loja_legacy_v1 "
            "(tenant_id, unidade_id, loja_id, ativo) "
            "values ('tenant-local', 'unidade-ambigua', 2, 1)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(RuntimeError, match="exatamente o mapping legado"):
        e2e_test_database.reset_database_in_place(db_path)
