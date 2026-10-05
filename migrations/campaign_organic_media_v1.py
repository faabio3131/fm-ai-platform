"""Migration 0068 — mídia de publicação orgânica no aggregate de campanhas."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "crm_rascunhos_campanha_v1"
_COLUMN = "midia_url"


def upgrade_campaign_organic_media_v1(connection: Connection) -> None:
    """Adiciona mídia opcional sem alterar rascunhos/campanhas legadas."""

    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("aggregate de campanhas ausente antes da migration 0068")

    columns = {str(column["name"]) for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        connection.execute(
            text(
                "ALTER TABLE crm_rascunhos_campanha_v1 "
                "ADD COLUMN midia_url TEXT NULL"
            )
        )

    final_columns = {
        str(column["name"])
        for column in inspect(connection).get_columns(_TABLE)
    }
    if _COLUMN not in final_columns:
        raise RuntimeError("midia_url ausente após migration 0068")
