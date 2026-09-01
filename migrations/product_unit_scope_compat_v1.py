"""Compatibilidade aditiva do escopo de unidade na tabela legada ``produtos``.

Algumas bases V1 anteriores já possuem ``produtos.loja_id`` como NOT NULL, enquanto
o contrato legado atual ainda não mapeava essa coluna. Esta migration não remove nem
relaxa constraints existentes. Em bases que ainda não possuem a coluna, cria-a como
anulável para preservar linhas históricas sem inventar unidade; novos registros do app
passam a informar explicitamente a unidade autenticada.
"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "produtos"
_COLUMN = "loja_id"
_INDEX = "ix_produtos_loja_id_v1"


def upgrade_product_unit_scope_compat_v1(connection: Connection) -> None:
    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError("tabela produtos ausente antes da migration de escopo de unidade")

    columns = {column["name"] for column in inspector.get_columns(_TABLE)}
    if _COLUMN not in columns:
        # Nullable de propósito: não atribuímos unidade fictícia a registros históricos.
        connection.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {_COLUMN} VARCHAR(64) NULL"))

    # Índice aditivo para permitir filtros por unidade sem alterar dados existentes.
    indexes = {index["name"] for index in inspect(connection).get_indexes(_TABLE)}
    if _INDEX not in indexes:
        connection.execute(text(f"CREATE INDEX {_INDEX} ON {_TABLE} ({_COLUMN})"))
