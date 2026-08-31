from sqlalchemy import create_engine, inspect

from migrations.manifest import assert_migration_manifest
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_0033_delivery_policy_esta_no_registry_manifest_e_cria_schema():
    assert DEFAULT_MIGRATIONS[-1].version == "0033_delivery_policy_v1"
    assert_migration_manifest(DEFAULT_MIGRATIONS)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    aplicadas = run_migrations(engine)

    assert aplicadas[-1] == "0033_delivery_policy_v1"
    tabelas = set(inspect(engine).get_table_names())
    assert "delivery_origem_unidade_v1" in tabelas
    assert "delivery_areas_v1" in tabelas
