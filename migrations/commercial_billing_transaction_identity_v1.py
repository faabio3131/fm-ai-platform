"""Migration 0061 — identidade comercial explícita por transação SaaS.

Materializa no ledger financeiro a identidade canônica do cliente/produto já
presente na assinatura. A migration não inventa vínculos para transações
históricas órfãs: faz backfill somente quando existe subscription_id resolvível.
Novas transações passam a ser endurecidas na aplicação para exigir esse vínculo.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TRANSACTION_TABLE = "fm_billing_transactions_v1"
_SUBSCRIPTION_TABLE = "fm_commercial_subscriptions_v1"
_PRODUCT_ACCOUNT_TABLE = "fm_product_accounts_v1"

_IDENTITY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("fm_customer_id", "VARCHAR(64)"),
    ("product_account_id", "VARCHAR(64)"),
    ("product_code", "VARCHAR(64)"),
    ("tenant_id", "VARCHAR(64)"),
)

_INDEXES: tuple[tuple[str, str], ...] = (
    (
        "ix_fm_billing_tx_customer_product_v1",
        "fm_customer_id, product_code, updated_at",
    ),
    (
        "ix_fm_billing_tx_product_account_v1",
        "product_account_id, updated_at",
    ),
    (
        "ix_fm_billing_tx_tenant_product_v1",
        "tenant_id, product_code, updated_at",
    ),
)


def _require_tables(connection: Connection) -> None:
    tables = set(inspect(connection).get_table_names())
    missing = {
        _TRANSACTION_TABLE,
        _SUBSCRIPTION_TABLE,
        _PRODUCT_ACCOUNT_TABLE,
    } - tables
    if missing:
        raise RuntimeError(
            "schema comercial incompleto antes da migration 0061: "
            + ", ".join(sorted(missing))
        )


def _add_identity_columns(connection: Connection) -> None:
    existing = {
        str(column["name"])
        for column in inspect(connection).get_columns(_TRANSACTION_TABLE)
    }
    for name, sql_type in _IDENTITY_COLUMNS:
        if name in existing:
            continue
        connection.execute(
            text(
                f"ALTER TABLE {_TRANSACTION_TABLE} "
                f"ADD COLUMN {name} {sql_type} NULL"
            )
        )


def _backfill_from_subscription(connection: Connection) -> None:
    for column in ("fm_customer_id", "product_account_id", "tenant_id"):
        connection.execute(
            text(
                f"""
                UPDATE {_TRANSACTION_TABLE}
                SET {column} = (
                    SELECT subscription.{column}
                    FROM {_SUBSCRIPTION_TABLE} AS subscription
                    WHERE subscription.subscription_id =
                          {_TRANSACTION_TABLE}.subscription_id
                )
                WHERE {column} IS NULL
                  AND subscription_id IS NOT NULL
                  AND EXISTS (
                    SELECT 1
                    FROM {_SUBSCRIPTION_TABLE} AS subscription
                    WHERE subscription.subscription_id =
                          {_TRANSACTION_TABLE}.subscription_id
                )
                """
            )
        )

    connection.execute(
        text(
            f"""
            UPDATE {_TRANSACTION_TABLE}
            SET product_code = (
                SELECT account.product_code
                FROM {_PRODUCT_ACCOUNT_TABLE} AS account
                WHERE account.product_account_id =
                      {_TRANSACTION_TABLE}.product_account_id
            )
            WHERE product_code IS NULL
              AND product_account_id IS NOT NULL
              AND EXISTS (
                SELECT 1
                FROM {_PRODUCT_ACCOUNT_TABLE} AS account
                WHERE account.product_account_id =
                      {_TRANSACTION_TABLE}.product_account_id
            )
            """
        )
    )


def _create_indexes(connection: Connection) -> None:
    existing = {
        str(index["name"])
        for index in inspect(connection).get_indexes(_TRANSACTION_TABLE)
    }
    for name, columns in _INDEXES:
        if name in existing:
            continue
        connection.execute(
            text(
                f"CREATE INDEX {name} "
                f"ON {_TRANSACTION_TABLE} ({columns})"
            )
        )


def _validate_linked_identity(connection: Connection) -> None:
    mismatches = int(
        connection.execute(
            text(
                f"""
                SELECT COUNT(*)
                FROM {_TRANSACTION_TABLE} AS transaction
                JOIN {_SUBSCRIPTION_TABLE} AS subscription
                  ON subscription.subscription_id = transaction.subscription_id
                JOIN {_PRODUCT_ACCOUNT_TABLE} AS account
                  ON account.product_account_id = subscription.product_account_id
                WHERE transaction.fm_customer_id IS NOT NULL
                  AND (
                    transaction.fm_customer_id <> subscription.fm_customer_id
                    OR transaction.product_account_id <>
                       subscription.product_account_id
                    OR transaction.tenant_id <> subscription.tenant_id
                    OR transaction.product_code <> account.product_code
                  )
                """
            )
        ).scalar_one()
    )
    if mismatches:
        raise RuntimeError(
            "ledger de billing contém identidade comercial divergente"
        )

    columns = {
        str(column["name"])
        for column in inspect(connection).get_columns(_TRANSACTION_TABLE)
    }
    missing_columns = {
        name for name, _ in _IDENTITY_COLUMNS if name not in columns
    }
    if missing_columns:
        raise RuntimeError(
            "migration 0061 não materializou colunas: "
            + ", ".join(sorted(missing_columns))
        )

    indexes = {
        str(index["name"])
        for index in inspect(connection).get_indexes(_TRANSACTION_TABLE)
    }
    missing_indexes = {
        name for name, _ in _INDEXES if name not in indexes
    }
    if missing_indexes:
        raise RuntimeError(
            "migration 0061 não materializou índices: "
            + ", ".join(sorted(missing_indexes))
        )


def upgrade_commercial_billing_transaction_identity_v1(
    connection: Connection,
) -> None:
    """Adiciona e reconcilia identidade comercial por pagamento sem inventar dono."""

    _require_tables(connection)
    _add_identity_columns(connection)
    _backfill_from_subscription(connection)
    _create_indexes(connection)
    _validate_linked_identity(connection)
