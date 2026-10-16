"""PostgreSQL 16 real: role independente com mínimos privilégios."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from migrations.runner import run_migrations
from scripts import cleanup_expired_operational_sessions as worker
from scripts.provision_session_cleanup_role import provision


def test_dedicated_postgres_role_can_only_purge_expired_sessions(
    monkeypatch, tmp_path
):
    import os

    admin_url = os.environ["DATABASE_URL"]
    assert "127.0.0.1" in admin_url
    admin = create_engine(admin_url)
    password = secrets.token_urlsafe(48)
    restricted = None
    try:
        run_migrations(admin)
        with admin.begin() as conn:
            now = datetime.now(UTC)
            conn.execute(
                text(
                    "INSERT INTO fm_operational_sessions_v1 "
                    "(session_id, usuario_id, identity_user_id, membership_id, "
                    "email, tenant_id, unidade_ativa_id, expira_em) "
                    "VALUES (:sid, 'u', 'i', 'm', 'u@domain.test', "
                    "'tenant', 'unit', :expiry)"
                ),
                [
                    {"sid": "expired-a", "expiry": now - timedelta(days=2)},
                    {"sid": "expired-b", "expiry": now - timedelta(hours=1)},
                    {"sid": "valid", "expiry": now + timedelta(hours=2)},
                ],
            )
        provision(admin_url=admin_url, password=password)
        url = make_url(admin_url).set(
            username=worker.ROLE_NAME,
            password=password,
        )
        restricted = create_engine(
            url, pool_size=1, max_overflow=0, pool_timeout=5
        )
        worker.verify_database_role(restricted)

        with restricted.connect() as conn:
            assert conn.execute(
                text("SELECT COUNT(*) FROM fm_operational_sessions_v1")
            ).scalar_one() == 3
            conn.rollback()
            with pytest.raises(ProgrammingError):
                conn.execute(
                    text("SELECT email FROM fm_operational_sessions_v1")
                )
            conn.rollback()
            with pytest.raises(ProgrammingError):
                conn.execute(text("SELECT usuario_id FROM fm_usuarios_v1"))
            conn.rollback()
            with pytest.raises(ProgrammingError):
                conn.execute(
                    text(
                        "UPDATE fm_operational_sessions_v1 "
                        "SET email='changed' WHERE session_id='valid'"
                    )
                )
            conn.rollback()

        monkeypatch.setenv("FM_AI_ENV", "staging")
        monkeypatch.setattr(worker, "build_engine", lambda settings: restricted)
        monkeypatch.setattr(
            worker, "load_runtime_settings", lambda: SimpleNamespace()
        )
        # Exercitar proteção de lote: nenhuma varredura/eliminações sem teto.
        with pytest.raises(ValueError, match="batch_limit"):
            worker.cleanup(batch_limit=worker.BATCH_LIMIT + 1)
        assert worker.cleanup(batch_limit=1, max_batches=1) == 1
        assert worker.cleanup(batch_limit=1, max_batches=2) == 1
        assert worker.cleanup(batch_limit=10, max_batches=2) == 0
        with admin.connect() as conn:
            ids = conn.execute(
                text("SELECT session_id FROM fm_operational_sessions_v1")
            ).scalars().all()
            assert ids == ["valid"]

        monkeypatch.setattr(worker, "build_engine", lambda settings: admin)
        with pytest.raises(RuntimeError, match="database_role_not_least_privilege"):
            worker.cleanup()
        with admin.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM fm_operational_sessions_v1")).scalar_one() == 1
    finally:
        if restricted is not None:
            restricted.dispose()
        admin.dispose()
