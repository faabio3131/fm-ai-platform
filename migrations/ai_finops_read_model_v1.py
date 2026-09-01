"""Migration aditiva do AI FinOps Read Model V1."""

from __future__ import annotations

from sqlalchemy.engine import Connection

from infra.ai_finops_models import AIFinOpsBase


def upgrade_ai_finops_read_model_v1(connection: Connection) -> None:
    AIFinOpsBase.metadata.create_all(bind=connection, checkfirst=True)
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_fm_ai_usage_projector_v1 "
        "ON fm_ai_usage_events_v1 (timestamp, usage_event_id)"
    )


def revert_ai_finops_read_model_v1(connection: Connection) -> None:
    connection.exec_driver_sql("DROP INDEX IF EXISTS ix_fm_ai_usage_projector_v1")
    AIFinOpsBase.metadata.drop_all(bind=connection, checkfirst=True)
