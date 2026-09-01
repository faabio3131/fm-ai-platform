from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, create_engine, text

from migrations.history_guard import schema_signature
from migrations.runner import run_migrations

_DATABASE_URL = os.getenv("FM_AI_SD1D_POSTGRES_URL", "")

pytestmark = pytest.mark.skipif(
    not _DATABASE_URL,
    reason="FM_AI_SD1D_POSTGRES_URL nao configurada",
)


@contextmanager
def _schema_engine(prefix: str) -> Iterator[Engine]:
    schema = f"{prefix}_{uuid.uuid4().hex[:12]}"
    admin = create_engine(_DATABASE_URL, future=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))

    engine = create_engine(
        _DATABASE_URL,
        future=True,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _prepare_legacy_store(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE lojas (
                    id INTEGER NOT NULL PRIMARY KEY,
                    nome_fantasia VARCHAR(255) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO lojas (id, nome_fantasia)
                VALUES (7, 'Loja legada preservada')
                """
            )
        )


def test_sd1d_postgres_fresh_upgrade_convergem_e_sao_idempotentes() -> None:
    with _schema_engine("sd1d_fresh") as fresh, _schema_engine(
        "sd1d_upgrade"
    ) as upgrade:
        _prepare_legacy_store(upgrade)

        fresh_applied = run_migrations(fresh)
        upgrade_applied = run_migrations(upgrade)

        assert fresh_applied == upgrade_applied
        assert run_migrations(fresh) == ()
        assert run_migrations(upgrade) == ()
        assert schema_signature(fresh) == schema_signature(upgrade)

        with upgrade.begin() as connection:
            preserved = connection.execute(
                text("SELECT id, nome_fantasia FROM lojas WHERE id = 7")
            ).one()
            assert tuple(preserved) == (7, "Loja legada preservada")
