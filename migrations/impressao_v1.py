"""Migration aditiva do spool de impressão V1; nunca toca banco real nesta PR."""

from pathlib import Path

from sqlalchemy import Engine

from core.impressao.modelos_orm import ImpressaoBase

TABELAS = tuple(ImpressaoBase.metadata.tables)


def _validar_engine_teste(engine: Engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("Migration Impressão V1 autorizada somente em SQLite teste")
    database = engine.url.database
    if database not in (None, "", ":memory:"):
        caminho = Path(str(database)).resolve()
        if caminho.name == "banco_erp_local.db" or "test" not in caminho.name.lower():
            raise RuntimeError("Banco deve ser explicitamente efêmero/teste")


def upgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    ImpressaoBase.metadata.create_all(engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    _validar_engine_teste(engine)
    ImpressaoBase.metadata.drop_all(engine, checkfirst=True)
