from __future__ import annotations

from sqlalchemy import create_engine, inspect

from migrations.runner import run_migrations

EXPECTED_TABLES = {
    "fm_customers_v1",
    "fm_product_accounts_v1",
    "fm_commercial_idempotency_v1",
    "fm_commercial_audit_v1",
    "fm_commercial_outbox_v1",
}


def test_kca01_fresh_schema_materializa_commercial_registry() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)

    inspector = inspect(engine)
    assert EXPECTED_TABLES <= set(inspector.get_table_names())

    customer_columns = {
        column["name"] for column in inspector.get_columns("fm_customers_v1")
    }
    assert {
        "fm_customer_id",
        "customer_code",
        "account_class",
        "status",
        "version",
    } <= customer_columns

    account_columns = {
        column["name"]
        for column in inspector.get_columns("fm_product_accounts_v1")
    }
    assert {
        "product_account_id",
        "fm_customer_id",
        "product_code",
        "product_tenant_id",
        "status",
        "version",
    } <= account_columns


def test_kca01_binding_product_tenant_tem_constraint_unica() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    run_migrations(engine)
    uniques = inspect(engine).get_unique_constraints("fm_product_accounts_v1")

    assert any(
        set(item.get("column_names") or ())
        == {"product_code", "product_tenant_id"}
        for item in uniques
    )
