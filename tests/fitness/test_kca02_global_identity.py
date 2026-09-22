from __future__ import annotations

from sqlalchemy import create_engine, inspect

from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


def test_kca02_migration_e_tabelas_estao_no_registry_canonico() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0050_global_identity_membership_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    tabelas = set(inspect(engine).get_table_names())

    assert {
        "fm_identity_users_v1",
        "fm_identity_memberships_v1",
        "fm_identity_membership_roles_v1",
        "fm_identity_membership_units_v1",
    } <= tabelas
