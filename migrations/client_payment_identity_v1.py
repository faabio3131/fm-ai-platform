"""Migration aditiva para dados mínimos de pagador no cadastro legado de clientes."""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

_TABLE = "clientes"
_COLUMNS = {
    "email": "VARCHAR(320)",
    "documento_fiscal": "VARCHAR(32)",
}


def upgrade_client_payment_identity_v1(connection: Connection) -> None:
    inspector = inspect(connection)
    if _TABLE not in inspector.get_table_names():
        raise RuntimeError(
            "tabela clientes ausente antes da migration de identidade de pagamento"
        )

    existentes = {column["name"] for column in inspector.get_columns(_TABLE)}
    for nome, tipo in _COLUMNS.items():
        if nome in existentes:
            continue
        connection.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {nome} {tipo}"))
        existentes.add(nome)
