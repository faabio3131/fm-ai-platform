"""Migration 0039 — ledger canônico append-only de cashback CRM."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Connection

from infra.crm.cashback_schema import (
    crm_cashback_movimentos_v1,
    crm_cashback_saldos_v1,
)

_SALDOS = "crm_cashback_saldos_v1"
_MOVIMENTOS = "crm_cashback_movimentos_v1"


def _validar_colunas(
    connection: Connection, tabela: str, esperadas: set[str]
) -> None:
    inspector = inspect(connection)
    atuais = {str(coluna["name"]) for coluna in inspector.get_columns(tabela)}
    ausentes = esperadas - atuais
    if ausentes:
        raise RuntimeError(
            f"{tabela} existente possui colunas ausentes: "
            + ", ".join(sorted(ausentes))
        )


def _validar_pk(
    connection: Connection, tabela: str, esperada: list[str]
) -> None:
    atual = list(
        inspect(connection).get_pk_constraint(tabela).get("constrained_columns") or []
    )
    if atual != esperada:
        raise RuntimeError(f"{tabela} existente possui primary key divergente")


def _validar_movimentos(connection: Connection) -> None:
    _validar_colunas(
        connection,
        _MOVIMENTOS,
        {
            "tenant_id",
            "unidade_id",
            "movimento_id",
            "cliente_id",
            "tipo",
            "valor",
            "origem",
            "referencia",
            "ocorrido_em",
            "idempotency_key",
        },
    )
    _validar_pk(
        connection,
        _MOVIMENTOS,
        ["tenant_id", "unidade_id", "movimento_id"],
    )
    inspector = inspect(connection)
    uniques = {
        tuple(item.get("column_names") or [])
        for item in inspector.get_unique_constraints(_MOVIMENTOS)
    }
    if ("tenant_id", "unidade_id", "idempotency_key") not in uniques:
        raise RuntimeError(
            "crm_cashback_movimentos_v1 sem unicidade de idempotencia"
        )
    indices = {
        item.get("name"): tuple(item.get("column_names") or [])
        for item in inspector.get_indexes(_MOVIMENTOS)
    }
    esperado = (
        "tenant_id",
        "unidade_id",
        "cliente_id",
        "ocorrido_em",
        "movimento_id",
    )
    if indices.get("ix_crm_cashback_movimentos_cliente_v1") != esperado:
        raise RuntimeError(
            "crm_cashback_movimentos_v1 sem indice historico esperado"
        )


def _validar_saldos(connection: Connection) -> None:
    _validar_colunas(
        connection,
        _SALDOS,
        {"tenant_id", "unidade_id", "cliente_id", "saldo", "versao"},
    )
    _validar_pk(
        connection,
        _SALDOS,
        ["tenant_id", "unidade_id", "cliente_id"],
    )


def upgrade_crm_cashback_ledger_v1(connection: Connection) -> None:
    """Cria ledger e projeção de saldo sem backfill automático do legado."""

    tabelas = set(inspect(connection).get_table_names())
    if "crm_clientes_v1" not in tabelas:
        raise RuntimeError(
            "tabela crm_clientes_v1 ausente antes da migration 0039"
        )

    if _SALDOS not in tabelas:
        crm_cashback_saldos_v1.create(bind=connection, checkfirst=True)
    tabelas = set(inspect(connection).get_table_names())
    if _MOVIMENTOS not in tabelas:
        crm_cashback_movimentos_v1.create(bind=connection, checkfirst=True)

    _validar_saldos(connection)
    _validar_movimentos(connection)
