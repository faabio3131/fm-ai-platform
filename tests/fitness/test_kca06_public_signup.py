from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_kca06_signup_migration_is_registered() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0054_commercial_signup_v1"
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    assert "fm_public_signup_intents_v1" in inspect(engine).get_table_names()
