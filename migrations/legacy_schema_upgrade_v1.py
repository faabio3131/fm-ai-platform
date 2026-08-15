"""Upgrade aditivo das tabelas legadas criadas antes do runner V1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Column, DateTime, Float, Integer, String, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn


@dataclass(frozen=True)
class LegacyColumn:
    table: str
    column: Column[Any]
    backfill: object | None = None
    legacy_source: str | None = None


# Auditoria do histórico dos modelos de app.py. Tabelas inteiramente novas são
# criadas pela 0003; esta relação contém cada coluna acrescentada ou renomeada
# enquanto uma versão anterior da mesma tabela podia continuar no banco.
LEGACY_COLUMNS: tuple[LegacyColumn, ...] = (
    LegacyColumn("clientes", Column("saldo_cashback", Float), 0.0),
    LegacyColumn("produtos", Column("imagem_path", String, nullable=True)),
    LegacyColumn("insumos", Column("unidade_medida", String), "un", "unidade"),
    LegacyColumn("insumos", Column("saldo_atual", Float), 0.0, "quantidade_atual"),
    LegacyColumn("insumos", Column("estoque_minimo", Float), 0.0, "alerta_minimo"),
    LegacyColumn("insumos", Column("custo_unitario", Float), 0.0),
    LegacyColumn("insumos", Column("data_fabricacao", DateTime, nullable=True)),
    LegacyColumn("insumos", Column("data_validade", DateTime, nullable=True)),
    LegacyColumn("insumos", Column("dias_alerta_vencimento", Integer), 15),
    LegacyColumn("vendas", Column("cliente_id", Integer, nullable=True)),
    LegacyColumn("vendas", Column("forma_pagamento", String), "Pix"),
    LegacyColumn("vendas", Column("status_pagamento", String), "Aprovado"),
    LegacyColumn("configuracoes_meta", Column("gateway_provider", String), "Mercado Pago"),
    LegacyColumn("configuracoes_meta", Column("gateway_pix_key", String, nullable=True)),
    LegacyColumn("configuracoes_meta", Column("gateway_api_key", String, nullable=True)),
)


def upgrade_legacy_schema_v1(connection: Connection) -> None:
    """Acrescenta colunas ausentes, mantendo dados e defaults semânticos do ORM."""

    preparadas: dict[str, set[str]] = {}
    preparadas_originais: dict[str, set[str]] = {}
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())

    for change in LEGACY_COLUMNS:
        if change.table not in tables:
            # A migration 0003 cria tabelas ausentes. A guarda também torna esta
            # unidade segura quando chamada isoladamente por ferramentas de teste.
            continue
        if change.table not in preparadas:
            existentes = {
                str(item["name"]) for item in inspector.get_columns(change.table)
            }
            preparadas[change.table] = set(existentes)
            preparadas_originais[change.table] = existentes
        if change.column.name in preparadas[change.table]:
            continue

        preparer = connection.dialect.identifier_preparer
        table_sql = preparer.quote(change.table)
        column_sql = str(CreateColumn(change.column).compile(dialect=connection.dialect))
        connection.exec_driver_sql(f"ALTER TABLE {table_sql} ADD COLUMN {column_sql}")
        preparadas[change.table].add(change.column.name)

        target = preparer.quote(change.column.name)
        source = change.legacy_source
        if source and source in preparadas_originais[change.table]:
            connection.execute(
                text(
                    f"UPDATE {table_sql} SET {target} = {preparer.quote(source)} "
                    f"WHERE {target} IS NULL"
                )
            )
        if change.backfill is not None:
            connection.execute(
                text(f"UPDATE {table_sql} SET {target} = :value WHERE {target} IS NULL"),
                {"value": change.backfill},
            )
