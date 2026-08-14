from __future__ import annotations

import importlib.util
import sqlite3
import threading
import time
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "e2e" / "test_database.py"
SPEC = importlib.util.spec_from_file_location("e2e_test_database", MODULE_PATH)
assert SPEC and SPEC.loader
e2e_test_database = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e2e_test_database)


def test_reset_database_preserves_file_and_restores_seed(tmp_path):
    db_path = tmp_path / "fm_ai_test.sqlite3"
    e2e_test_database.initialize_database(db_path)
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
        assert cursor.execute("pragma foreign_key_check").fetchall() == []
    finally:
        cursor.close()
        connection.close()


def test_reset_database_retries_a_temporary_lock(tmp_path):
    db_path = tmp_path / "fm_ai_test.sqlite3"
    e2e_test_database.initialize_database(db_path)
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

    e2e_test_database.initialize_database(db_path)
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
