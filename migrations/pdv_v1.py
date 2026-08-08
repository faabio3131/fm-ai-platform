"""Migration aditiva PR8; exige Engine SQLite explicitamente efemera/de teste."""

from pathlib import Path

from sqlalchemy import Engine

from core.pdv.modelos_orm import PDVBase

TABELAS = tuple(PDVBase.metadata.tables)


def _validar(engine: Engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        raise RuntimeError("PDV V1 autorizado somente em SQLite de teste")
    banco = engine.url.database
    if banco not in (None, "", ":memory:"):
        caminho = Path(str(banco)).resolve()
        if caminho.name == "banco_erp_local.db" or not any(
            token in str(caminho).lower() for token in ("test", ".tmp", "temp")
        ):
            raise RuntimeError("Banco PDV deve ser explicitamente temporario")


def upgrade(engine: Engine) -> None:
    _validar(engine)
    PDVBase.metadata.create_all(engine, checkfirst=True)


def downgrade(engine: Engine) -> None:
    _validar(engine)
    PDVBase.metadata.drop_all(engine, checkfirst=True)
