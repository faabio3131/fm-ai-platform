"""Migration aditiva 0070: ledger de reservas de IA separado do ERP."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from infra.ai_budget_sqlalchemy import AIBudgetBase


def upgrade_ai_franchise_budget_v1(connection: Connection) -> None:
    AIBudgetBase.metadata.create_all(bind=connection, checkfirst=True)


def revert_ai_franchise_budget_v1(connection: Connection) -> None:
    """Rollback apenas de tabelas vazias, para nao apagar patrimonio financeiro."""
    for table in AIBudgetBase.metadata.sorted_tables:
        if connection.execute(select(func.count()).select_from(table)).scalar_one():
            raise RuntimeError("rollback_ai_franchise_exige_tabelas_vazias")
    AIBudgetBase.metadata.drop_all(bind=connection, checkfirst=True)
