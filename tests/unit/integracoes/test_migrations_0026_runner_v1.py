from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from migrations.crm_clientes_persistencia_v1 import (
    upgrade_crm_clientes_persistencia_v1,
)
from migrations.crm_consentimentos_historico_v1 import (
    upgrade_crm_consentimentos_historico_v1,
)
from migrations.runner import (
    DEFAULT_MIGRATIONS,
    Migration,
    applied_versions,
    run_migrations,
)


def _engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
    )

    with engine.begin() as connection:
        connection.execute(
            text("PRAGMA foreign_keys = ON")
        )

    return engine


def test_default_runner_ordena_crm_0022_ate_0026():
    versoes = [
        migration.version
        for migration in DEFAULT_MIGRATIONS
    ]

    esperadas = [
        "0022_crm_clientes_persistencia_v1",
        "0023_crm_contact_vault_v1",
        "0024_crm_cliente_legado_mapping_v1",
        "0025_crm_contact_ownership_v1",
        "0026_crm_consentimentos_historico_v1",
    ]

    indices = [
        versoes.index(versao)
        for versao in esperadas
    ]

    assert indices == list(
        range(indices[0], indices[0] + len(esperadas))
    )


def test_runner_aplica_0022_e_0026_e_nao_reaplica():
    engine = _engine()

    migrations = (
        Migration(
            "0022_crm_clientes_persistencia_v1",
            upgrade_crm_clientes_persistencia_v1,
        ),
        Migration(
            "0026_crm_consentimentos_historico_v1",
            upgrade_crm_consentimentos_historico_v1,
        ),
    )

    primeira = run_migrations(
        engine,
        migrations=migrations,
    )

    segunda = run_migrations(
        engine,
        migrations=migrations,
    )

    assert primeira == (
        "0022_crm_clientes_persistencia_v1",
        "0026_crm_consentimentos_historico_v1",
    )

    assert segunda == ()

    with engine.begin() as connection:
        versoes = applied_versions(connection)
        tabelas = set(
            inspect(connection).get_table_names()
        )

    assert "0022_crm_clientes_persistencia_v1" in versoes
    assert "0026_crm_consentimentos_historico_v1" in versoes

    assert "crm_clientes_v1" in tabelas
    assert "crm_consentimentos_v1" in tabelas
