from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from migrations.salao_v1 import TABELAS, downgrade, upgrade


def test_upgrade_downgrade_em_memoria() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    nomes = set(inspect(engine).get_table_names())
    assert set(TABELAS) <= nomes
    downgrade(engine)
    nomes = set(inspect(engine).get_table_names())
    assert not (set(TABELAS) & nomes)


def test_migration_recusa_banco_sem_marcacao_de_teste(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'banco_erp_local.db'}")
    with pytest.raises(RuntimeError, match="efemero/teste"):
        upgrade(engine)
