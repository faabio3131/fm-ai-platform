from sqlalchemy import create_engine, inspect, text

from migrations.crm_clientes_persistencia_v1 import (
    upgrade_crm_clientes_persistencia_v1,
)
from migrations.runner import (
    Migration,
    applied_versions,
    run_migrations,
)
from migrations.unit_legacy_store_mapping_v1 import (
    upgrade_unit_legacy_store_mapping_v1,
)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
    )

    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))
        conn.execute(
            text(
                """
                CREATE TABLE lojas (
                    id INTEGER PRIMARY KEY,
                    nome_fantasia VARCHAR NOT NULL
                )
                """
            )
        )

    return engine


_MIGRATIONS = (
    Migration(
        "0021_unit_legacy_store_mapping_v1",
        upgrade_unit_legacy_store_mapping_v1,
    ),
    Migration(
        "0022_crm_clientes_persistencia_v1",
        upgrade_crm_clientes_persistencia_v1,
    ),
)


def test_runner_aplica_0021_e_0022_na_ordem():
    engine = _engine()

    aplicadas = run_migrations(
        engine,
        migrations=_MIGRATIONS,
    )

    assert aplicadas == (
        "0021_unit_legacy_store_mapping_v1",
        "0022_crm_clientes_persistencia_v1",
    )

    with engine.begin() as conn:
        versoes = applied_versions(conn)
        tabelas = set(inspect(conn).get_table_names())

    assert "0021_unit_legacy_store_mapping_v1" in versoes
    assert "0022_crm_clientes_persistencia_v1" in versoes

    assert "fm_unidade_loja_legacy_v1" in tabelas
    assert "crm_clientes_v1" in tabelas
    assert "crm_cliente_contatos_v1" in tabelas


def test_runner_nao_reaplica_0021_e_0022():
    engine = _engine()

    primeira = run_migrations(
        engine,
        migrations=_MIGRATIONS,
    )

    segunda = run_migrations(
        engine,
        migrations=_MIGRATIONS,
    )

    assert primeira == (
        "0021_unit_legacy_store_mapping_v1",
        "0022_crm_clientes_persistencia_v1",
    )
    assert segunda == ()


def test_runner_preserva_registros_ao_reexecutar():
    engine = _engine()

    run_migrations(
        engine,
        migrations=_MIGRATIONS,
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO crm_clientes_v1 (
                    tenant_id,
                    unidade_id,
                    cliente_id,
                    origem,
                    criado_em,
                    versao
                )
                VALUES (
                    'tenant-a',
                    'unidade-a',
                    'cliente-1',
                    'manual',
                    CURRENT_TIMESTAMP,
                    1
                )
                """
            )
        )

    run_migrations(
        engine,
        migrations=_MIGRATIONS,
    )

    with engine.begin() as conn:
        total = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM crm_clientes_v1
                WHERE tenant_id = 'tenant-a'
                  AND unidade_id = 'unidade-a'
                  AND cliente_id = 'cliente-1'
                """
            )
        ).scalar_one()

    assert total == 1
