"""Migration 0026 — autoridade histórica de consentimentos CRM.

Cria somente o histórico canônico append-only.
Não realiza backfill.
Não promove crm_consentimentos_atuais_v1 a autoridade.
Não cria Outbox paralela.
"""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from infra.crm.consentimentos_schema import crm_consentimentos_v1

TABLE_NAME = "crm_consentimentos_v1"

_REQUIRED_COLUMNS = {
    "registro_seq",
    "consentimento_id",
    "tenant_id",
    "unidade_id",
    "cliente_id",
    "canal",
    "finalidade",
    "status",
    "base_legal",
    "texto_versao",
    "origem",
    "prova_hash",
    "ocorrido_em",
    "idempotency_key",
    "correlation_id",
    "concedido_em",
    "revogado_em",
}

_REQUIRED_UNIQUES = {
    "uq_crm_consentimentos_scope_id_v1": [
        "tenant_id",
        "unidade_id",
        "consentimento_id",
    ],
    "uq_crm_consentimentos_scope_idem_v1": [
        "tenant_id",
        "unidade_id",
        "idempotency_key",
    ],
}

_REQUIRED_INDEXES = {
    "ix_crm_consentimentos_cliente_v1": [
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "registro_seq",
    ],
    "ix_crm_consentimentos_atual_v1": [
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "canal",
        "finalidade",
        "ocorrido_em",
        "registro_seq",
    ],
    "ix_crm_consentimentos_audiencia_v1": [
        "tenant_id",
        "unidade_id",
        "canal",
        "finalidade",
        "ocorrido_em",
        "registro_seq",
    ],
}

_REQUIRED_FK_COLUMNS = [
    "tenant_id",
    "unidade_id",
    "cliente_id",
]

_REQUIRED_FK_REFERRED_COLUMNS = [
    "tenant_id",
    "unidade_id",
    "cliente_id",
]


def _validar_schema_existente(connection: Connection) -> None:
    inspector = inspect(connection)

    colunas = {
        coluna["name"]
        for coluna in inspector.get_columns(TABLE_NAME)
    }

    ausentes = _REQUIRED_COLUMNS - colunas

    if ausentes:
        raise RuntimeError(
            "crm_consentimentos_v1 existente possui colunas ausentes: "
            + ", ".join(sorted(ausentes))
        )

    pk = inspector.get_pk_constraint(TABLE_NAME)
    pk_colunas = list(pk.get("constrained_columns") or [])

    if pk_colunas != ["registro_seq"]:
        raise RuntimeError(
            "crm_consentimentos_v1 existente possui primary key divergente"
        )

    fk_encontrada = False

    for fk in inspector.get_foreign_keys(TABLE_NAME):
        constrained = list(fk.get("constrained_columns") or [])
        referred = list(fk.get("referred_columns") or [])

        if constrained != _REQUIRED_FK_COLUMNS:
            continue

        fk_encontrada = True

        if (
            fk.get("referred_table") != "crm_clientes_v1"
            or referred != _REQUIRED_FK_REFERRED_COLUMNS
        ):
            raise RuntimeError(
                "crm_consentimentos_v1 existente possui FK "
                "ClienteCRM divergente"
            )

        break

    if not fk_encontrada:
        raise RuntimeError(
            "crm_consentimentos_v1 existente nao possui FK "
            "ClienteCRM scoped obrigatoria"
        )

    uniques_refletidas = inspector.get_unique_constraints(TABLE_NAME)

    unique_por_nome = {
        item["name"]: list(item.get("column_names") or [])
        for item in uniques_refletidas
        if item.get("name")
    }

    unique_shapes = {
        tuple(item.get("column_names") or [])
        for item in uniques_refletidas
    }

    sqlite = connection.dialect.name == "sqlite"

    for nome, colunas_esperadas in _REQUIRED_UNIQUES.items():
        colunas_por_nome = unique_por_nome.get(nome)

        if colunas_por_nome is not None:
            if colunas_por_nome != colunas_esperadas:
                raise RuntimeError(
                    "crm_consentimentos_v1 existente possui constraint "
                    f"de unicidade divergente: {nome}"
                )
            continue

        # SQLite nem sempre preserva o nome de UNIQUE CONSTRAINTS
        # criadas por SQL bruto durante reflection. Nos testes SQLite,
        # validamos o shape estrutural. Em banco comercial/PostgreSQL,
        # o nome também é parte do contrato esperado.
        if sqlite:
            if tuple(colunas_esperadas) not in unique_shapes:
                raise RuntimeError(
                    "crm_consentimentos_v1 existente possui constraint "
                    f"de unicidade divergente ou ausente: {nome}"
                )
            continue

        raise RuntimeError(
            "crm_consentimentos_v1 existente possui constraint "
            f"de unicidade ausente: {nome}"
        )

    indices = {
        item["name"]: {
            "columns": list(item.get("column_names") or []),
            "unique": bool(item.get("unique")),
        }
        for item in inspector.get_indexes(TABLE_NAME)
        if item.get("name")
    }

    for nome, colunas_esperadas in _REQUIRED_INDEXES.items():
        indice = indices.get(nome)

        if indice is None:
            raise RuntimeError(
                "crm_consentimentos_v1 existente possui indice ausente: "
                f"{nome}"
            )

        if (
            indice["columns"] != colunas_esperadas
            or indice["unique"]
        ):
            raise RuntimeError(
                "crm_consentimentos_v1 existente possui indice "
                f"divergente: {nome}"
            )




def upgrade_crm_consentimentos_historico_v1(
    connection: Connection,
) -> None:
    """Cria e valida a autoridade append-only sem migrar dados existentes."""

    inspector = inspect(connection)

    if "crm_clientes_v1" not in inspector.get_table_names():
        raise RuntimeError(
            "tabela crm_clientes_v1 ausente antes da migration 0026"
        )

    if TABLE_NAME not in inspector.get_table_names():
        crm_consentimentos_v1.create(
            bind=connection,
            checkfirst=True,
        )

    _validar_schema_existente(connection)
