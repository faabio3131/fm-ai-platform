"""Reconciliação completa e aditiva do schema ORM legado da V1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Column, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn

from infra.legacy_schema import legacy_metadata


@dataclass(frozen=True)
class Backfill:
    value: object | None = None
    legacy_source: str | None = None


_BACKFILLS: dict[tuple[str, str], Backfill] = {
    ("clientes", "ultima_compra"): Backfill(value=datetime.now),
    ("clientes", "total_gasto"): Backfill(value=0.0),
    ("clientes", "saldo_cashback"): Backfill(value=0.0),
    ("clientes", "status"): Backfill(value="Ativo"),
    ("insumos", "unidade_medida"): Backfill(value="un", legacy_source="unidade"),
    ("insumos", "saldo_atual"): Backfill(
        value=0.0, legacy_source="quantidade_atual"
    ),
    ("insumos", "estoque_minimo"): Backfill(
        value=0.0, legacy_source="alerta_minimo"
    ),
    ("insumos", "custo_unitario"): Backfill(value=0.0),
    ("insumos", "dias_alerta_vencimento"): Backfill(value=15),
    ("fichas_tecnicas", "quantidade_utilizada"): Backfill(value=0.0),
    ("vendas", "quantidade"): Backfill(value=1),
    ("vendas", "valor_total"): Backfill(value=0.0),
    ("vendas", "custo_total"): Backfill(value=0.0, legacy_source="cmv_total"),
    ("vendas", "forma_pagamento"): Backfill(value="Pix"),
    ("vendas", "status_pagamento"): Backfill(value="Aprovado"),
    ("vendas", "data_venda"): Backfill(value=datetime.now, legacy_source="data_hora"),
    ("gateway_config", "gateway_provider"): Backfill(value="Mercado Pago"),
    ("gateway_config", "ambiente"): Backfill(value="Sandbox"),
    ("configuracoes_meta", "gateway_provider"): Backfill(value="Mercado Pago"),
    ("contatos_gerenciais", "receber_alertas_estoque"): Backfill(value=1),
}


def _backfill_value(backfill: Backfill) -> object | None:
    return backfill.value() if callable(backfill.value) else backfill.value


def reconcile_legacy_schema_v1(connection: Connection) -> None:
    """Adiciona toda coluna ORM ausente em uma tabela legada já existente.

    Colunas são inicialmente adicionadas como anuláveis para que linhas históricas
    nunca sejam descartadas ou invalidem o ``ALTER TABLE``. Tabelas novas continuam
    recebendo nullability e constraints integrais pela migration 0003.
    """

    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    preparer = connection.dialect.identifier_preparer

    for table in legacy_metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {
            str(item["name"]) for item in inspector.get_columns(table.name)
        }
        original_columns = set(existing_columns)
        table_sql = preparer.quote(table.name)

        for expected in table.columns:
            if expected.name in existing_columns:
                continue

            # ADD COLUMN com NOT NULL não é seguro para tabelas povoadas. A
            # nullability relaxada é compatível com leituras ORM e preserva linhas;
            # defaults semânticos são materializados logo abaixo quando existentes.
            additive_column: Column[Any] = Column(
                expected.name,
                expected.type,
                nullable=True,
            )
            column_sql = str(
                CreateColumn(additive_column).compile(dialect=connection.dialect)
            )
            connection.exec_driver_sql(
                f"ALTER TABLE {table_sql} ADD COLUMN {column_sql}"
            )
            existing_columns.add(expected.name)

            target = preparer.quote(expected.name)
            backfill = _BACKFILLS.get((table.name, expected.name))
            if backfill is None:
                continue
            source = backfill.legacy_source
            if source and source in original_columns:
                connection.execute(
                    text(
                        f"UPDATE {table_sql} SET {target} = {preparer.quote(source)} "
                        f"WHERE {target} IS NULL"
                    )
                )
            value = _backfill_value(backfill)
            if value is not None:
                connection.execute(
                    text(
                        f"UPDATE {table_sql} SET {target} = :value "
                        f"WHERE {target} IS NULL"
                    ),
                    {"value": value},
                )

        # Versões antigas de vendas identificavam o produto pelo nome. A relação
        # pode ser recuperada sem inventar IDs e sem sobrescrever vínculos válidos.
        if (
            table.name == "vendas"
            and "produto_id" in existing_columns
            and "produto_nome" in original_columns
            and "produtos" in existing_tables
        ):
            connection.execute(
                text(
                    "UPDATE vendas SET produto_id = ("
                    "SELECT produtos.id FROM produtos "
                    "WHERE produtos.nome = vendas.produto_nome"
                    ") WHERE produto_id IS NULL"
                )
            )
