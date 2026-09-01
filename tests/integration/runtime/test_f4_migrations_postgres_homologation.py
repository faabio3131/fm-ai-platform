from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, create_engine, inspect, text

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


def test_f4_migrations_0034_0035_aplicam_em_postgres_real_e_sao_idempotentes() -> None:
    with _schema_engine("f4_homolog") as engine:
        aplicadas = run_migrations(engine)

        assert "0034_crm_customer_context_v1" in aplicadas
        assert "0035_assistente_channel_runtime_v1" in aplicadas
        assert run_migrations(engine) == ()

        insp = inspect(engine)
        tabelas = set(insp.get_table_names())
        assert "crm_enderecos_seguros_v1" in tabelas
        assert "assistente_canal_conversas_v1" in tabelas
        assert "fm_schema_migrations" in tabelas

        with engine.begin() as connection:
            versions = set(
                connection.execute(
                    text(
                        "SELECT version FROM fm_schema_migrations "
                        "WHERE version IN "
                        "('0034_crm_customer_context_v1', "
                        "'0035_assistente_channel_runtime_v1')"
                    )
                ).scalars()
            )
        assert versions == {
            "0034_crm_customer_context_v1",
            "0035_assistente_channel_runtime_v1",
        }
