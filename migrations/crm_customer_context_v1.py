"""Migration 0034 — Customer Context cifrado para endereços autorizados."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from infra.crm.enderecos_schema import crm_enderecos_seguros_v1


def upgrade_crm_customer_context_v1(connection: Connection) -> None:
    """Cria somente o vault de endereços após ClienteCRM existir."""

    if "crm_clientes_v1" not in inspect(connection).get_table_names():
        raise RuntimeError(
            "tabela crm_clientes_v1 ausente antes da migration 0034"
        )
    crm_enderecos_seguros_v1.create(
        bind=connection,
        checkfirst=True,
    )
