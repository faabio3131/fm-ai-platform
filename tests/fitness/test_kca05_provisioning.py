from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

EXPECTED_TABLES = {
    "fm_commercial_provisioning_sagas_v1",
    "fm_commercial_provisioning_inbox_v1",
}


def test_kca05_migration_e_tabelas_estao_no_registry_canonico() -> None:
    versions = tuple(migration.version for migration in DEFAULT_MIGRATIONS)
    assert "0053_commercial_provisioning_v1" in versions
    assert versions.index("0053_commercial_provisioning_v1") < versions.index(
        "0054_commercial_signup_v1"
    )

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
