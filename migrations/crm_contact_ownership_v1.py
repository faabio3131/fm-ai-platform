"""Ownership canônico de referências de contato do ClienteCRM.

Garante que uma mesma referência segura possua no máximo um proprietário
ClienteCRM dentro do mesmo tenant/unidade.

Não corrige, remove ou escolhe silenciosamente registros conflitantes.
"""

from __future__ import annotations

from sqlalchemy import (
    Index,
    MetaData,
    Table,
    func,
    inspect,
    select,
)
from sqlalchemy.engine import Connection

INDEX_NAME = "uq_crm_cliente_contato_scope_ref_owner_v1"
TABLE_NAME = "crm_cliente_contatos_v1"

INDEX_COLUMNS = [
    "tenant_id",
    "unidade_id",
    "referencia",
]


def upgrade_crm_contact_ownership_v1(
    connection: Connection,
) -> None:
    inspector = inspect(connection)

    if TABLE_NAME not in inspector.get_table_names():
        raise RuntimeError(
            "tabela crm_cliente_contatos_v1 ausente "
            "antes da migration de ownership"
        )

    indices = {
        indice["name"]: indice
        for indice in inspector.get_indexes(TABLE_NAME)
    }

    existente = indices.get(INDEX_NAME)

    if existente is not None:
        colunas = existente.get("column_names") or []

        if (
            list(colunas) != INDEX_COLUMNS
            or not bool(existente.get("unique"))
        ):
            raise RuntimeError(
                "indice de ownership CRM existente "
                "possui definicao divergente"
            )

        return

    metadata = MetaData()

    contatos = Table(
        TABLE_NAME,
        metadata,
        autoload_with=connection,
    )

    conflito = connection.execute(
        select(
            contatos.c.tenant_id,
            contatos.c.unidade_id,
            contatos.c.referencia,
            func.count().label("quantidade"),
        )
        .group_by(
            contatos.c.tenant_id,
            contatos.c.unidade_id,
            contatos.c.referencia,
        )
        .having(func.count() > 1)
        .limit(1)
    ).first()

    if conflito is not None:
        raise RuntimeError(
            "ownership de contato CRM ambiguo; "
            "regularizacao explicita obrigatoria antes da 0025"
        )

    indice = Index(
        INDEX_NAME,
        contatos.c.tenant_id,
        contatos.c.unidade_id,
        contatos.c.referencia,
        unique=True,
    )

    indice.create(
        bind=connection,
        checkfirst=True,
    )
