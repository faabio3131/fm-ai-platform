"""Migration 0062 — tipo de titular configurável da conta recebedora SaaS."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "fm_billing_provider_accounts_v1"
_COLUMN = "legal_entity_type"


def upgrade_commercial_billing_provider_legal_entity_v1(
    connection: Connection,
) -> None:
    """Adiciona PF/PJ provider-neutral sem inventar titular para contas existentes."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError(
            "billing provider accounts ausente antes da migration 0062"
        )

    columns = {
        str(column["name"])
        for column in inspector.get_columns(_TABLE)
    }
    if _COLUMN not in columns:
        connection.execute(
            text(
                "ALTER TABLE fm_billing_provider_accounts_v1 "
                "ADD COLUMN legal_entity_type VARCHAR(16) NULL "
                "CHECK (legal_entity_type IS NULL "
                "OR legal_entity_type IN ('individual','company'))"
            )
        )

    final_columns = {
        str(column["name"])
        for column in inspect(connection).get_columns(_TABLE)
    }
    if _COLUMN not in final_columns:
        raise RuntimeError(
            "billing provider legal_entity_type ausente após migration 0062"
        )

    invalid = int(
        connection.execute(
            text(
                "SELECT COUNT(*) FROM fm_billing_provider_accounts_v1 "
                "WHERE legal_entity_type IS NOT NULL "
                "AND legal_entity_type NOT IN ('individual','company')"
            )
        ).scalar_one()
    )
    if invalid:
        raise RuntimeError(
            "billing provider account contém legal_entity_type inválido"
        )
