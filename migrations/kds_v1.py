"""Migration aditiva do KDS V1; nunca toca banco real nesta PR."""

from pathlib import Path

from sqlalchemy import Engine

from core.kds.modelos_orm import KDSBase

TABELAS = tuple(KDSBase.metadata.tables)


def _validar_engine_teste(engine: Engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("Migration KDS V1 autorizada somente em SQLite teste")
    database = engine.url.database
    if database not in (None, "", ":memory:"):
        caminho = Path(str(database)).resolve()
        if caminho.name == "banco_erp_local.db" or "test" not in caminho.name.lower():
            raise RuntimeError("Banco deve ser explicitamente efemero/teste")


def upgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    KDSBase.metadata.create_all(engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    KDSBase.metadata.drop_all(engine, checkfirst=True)
