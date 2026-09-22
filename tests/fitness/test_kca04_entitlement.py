from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

EXPECTED_TABLES = {
    "fm_commercial_entitlement_snapshots_v1",
    "fm_kordena_entitlement_projection_v1",
    "fm_kordena_entitlement_inbox_v1",
}


def test_kca04_migration_e_tabelas_estao_no_registry_canonico() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0052_commercial_entitlement_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
