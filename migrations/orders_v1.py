"""Migration aditiva Pedido V1.

Recebe uma Engine criada explicitamente pelo chamador; nunca le DATABASE_URL.
"""

from pathlib import Path

from sqlalchemy import Engine

from core.pedidos.modelos_orm import OrdersBase

TABELAS = tuple(OrdersBase.metadata.tables)


def _validar_engine_teste(engine: Engine) -> None:
    url = engine.url
    if url.get_backend_name() != "sqlite":
        raise RuntimeError("Migration V1 autorizada somente em SQLite efemero/teste")
    database = url.database
    if database not in (None, "", ":memory:"):
        assert database is not None
        caminho = Path(database).resolve()
        if caminho.name == "banco_erp_local.db" or "test" not in caminho.name.lower():
            raise RuntimeError(
                "URL deve apontar explicitamente para banco efemero/teste"
            )


def upgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    OrdersBase.metadata.create_all(engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    OrdersBase.metadata.drop_all(engine, checkfirst=True)
