"""Reconcilia unidades administrativas sem ponte explícita para o catálogo legado.

A migration não tenta adivinhar qual loja histórica pertence a uma unidade. Para
cada unidade canônica sem vínculo, cria uma loja legada nova e exclusiva e grava
a ponte tenant/unidade -> loja. Isso restaura o catálogo de forma fail-closed sem
reaproveitar dados de outro escopo.
"""

from __future__ import annotations

from sqlalchemy import MetaData, Table, inspect, insert, select
from sqlalchemy.engine import Connection

_MAPPING_TABLE = "fm_unidade_loja_legacy_v1"
_UNITS_TABLE = "fm_unidades_admin_v1"
_STORES_TABLE = "lojas"


def upgrade_admin_unit_legacy_store_reconciliation_v1(
    connection: Connection,
) -> None:
    tables = set(inspect(connection).get_table_names())
    required = {_MAPPING_TABLE, _UNITS_TABLE, _STORES_TABLE}
    missing = sorted(required - tables)
    if missing:
        raise RuntimeError(
            "estrutura ausente para reconciliar escopo de catálogo: "
            + ", ".join(missing)
        )

    metadata = MetaData()
    mapping = Table(_MAPPING_TABLE, metadata, autoload_with=connection)
    units = Table(_UNITS_TABLE, metadata, autoload_with=connection)
    stores = Table(_STORES_TABLE, metadata, autoload_with=connection)

    rows = connection.execute(
        select(
            units.c.tenant_id,
            units.c.unidade_id,
            units.c.nome_fantasia,
        ).order_by(units.c.tenant_id, units.c.unidade_id)
    ).all()

    for row in rows:
        exists = connection.execute(
            select(mapping.c.loja_id)
            .where(mapping.c.tenant_id == row.tenant_id)
            .where(mapping.c.unidade_id == row.unidade_id)
        ).scalar_one_or_none()
        if exists is not None:
            continue

        nome = " ".join(str(row.nome_fantasia or row.unidade_id).split())
        store_id = connection.execute(
            insert(stores)
            .values(nome_fantasia=nome or str(row.unidade_id))
            .returning(stores.c.id)
        ).scalar_one()

        connection.execute(
            insert(mapping).values(
                tenant_id=str(row.tenant_id),
                unidade_id=str(row.unidade_id),
                loja_id=int(store_id),
                ativo=True,
            )
        )
