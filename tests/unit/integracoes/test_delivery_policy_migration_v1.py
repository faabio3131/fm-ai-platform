from sqlalchemy import create_engine, inspect

from migrations.manifest import assert_migration_manifest
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_0033_delivery_policy_esta_no_registry_manifest_e_cria_schema():
    versoes = [migration.version for migration in DEFAULT_MIGRATIONS]
    assert "0033_delivery_policy_v1" in versoes
    assert versoes.index("0033_delivery_policy_v1") < len(versoes)
    assert_migration_manifest(DEFAULT_MIGRATIONS)

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    aplicadas = run_migrations(engine)

    assert "0033_delivery_policy_v1" in aplicadas
    tabelas = set(inspect(engine).get_table_names())
    assert "delivery_origem_unidade_v1" in tabelas
    assert "delivery_areas_v1" in tabelas
