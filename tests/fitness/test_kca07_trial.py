from sqlalchemy import create_engine, inspect, select

from core.comercial.trial import TRIAL_DURATION_DAYS, TRIAL_POLICY_VERSION
from infra.comercial.trial_orm import FMCommercialTrialPolicyORM
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations


EXPECTED_TABLES = {
    "fm_commercial_trial_policies_v1",
    "fm_commercial_trials_v1",
}


def test_kca07_trial_migration_and_policy_are_canonical() -> None:
    versions = tuple(migration.version for migration in DEFAULT_MIGRATIONS)
    assert "0055_commercial_trial_v1" in versions
    assert versions.index("0055_commercial_trial_v1") < versions.index(
        "0056_commercial_subscription_v1"
    )

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())

    with engine.begin() as connection:
        policy = connection.execute(
            select(FMCommercialTrialPolicyORM.__table__).where(
                FMCommercialTrialPolicyORM.policy_version == TRIAL_POLICY_VERSION
            )
        ).mappings().one()
    assert policy["duration_days"] == TRIAL_DURATION_DAYS == 30
    assert policy["active"] is True
