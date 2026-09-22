from __future__ import annotations

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from infra.comercial.catalogo_orm import FMCommercialPlanORM
from migrations.runner import DEFAULT_MIGRATIONS, run_migrations

EXPECTED_TABLES = {
    "fm_commercial_plans_v1",
    "fm_commercial_plan_versions_v1",
    "fm_commercial_plan_entitlements_v1",
    "fm_commercial_prices_v1",
    "fm_commercial_promotions_v1",
    "fm_commercial_promotion_versions_v1",
    "fm_commercial_promotion_plans_v1",
}


def test_kca03_migration_e_tabelas_estao_no_registry_canonico() -> None:
    assert DEFAULT_MIGRATIONS[-1].version == "0051_commercial_catalog_v1"

    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())


def test_kordena_tem_exatamente_quatro_planos_canonicos_sem_preco_seed() -> None:
    engine = create_engine("sqlite:///:memory:")
    run_migrations(engine)

    with Session(engine) as session:
        plans = session.scalars(
            select(FMCommercialPlanORM).order_by(FMCommercialPlanORM.rank)
        ).all()

    assert [(row.plan_code, row.rank) for row in plans] == [
        ("KORDENA_PLAN_A", 1),
        ("KORDENA_PLAN_B", 2),
        ("KORDENA_PLAN_C", 3),
        ("KORDENA_PLAN_D", 4),
    ]

    inspector = inspect(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM fm_commercial_plan_versions_v1"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT COUNT(*) FROM fm_commercial_prices_v1"
        ).scalar_one() == 0
