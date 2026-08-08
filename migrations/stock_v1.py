"""Migration aditiva do estoque V1; nunca resolve configuracao da aplicacao."""

from pathlib import Path

from sqlalchemy import Engine

from core.estoque.modelos_orm import StockBase

TABELAS = tuple(StockBase.metadata.tables)


def _validar_engine_teste(engine: Engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("Migration estoque V1 autorizada somente em SQLite teste")
    database = engine.url.database
    if database not in (None, "", ":memory:"):
        caminho = Path(str(database)).resolve()
        if caminho.name == "banco_erp_local.db" or "test" not in caminho.name.lower():
            raise RuntimeError("Banco deve ser explicitamente efemero/teste")


def upgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    StockBase.metadata.create_all(engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    StockBase.metadata.drop_all(engine, checkfirst=True)
