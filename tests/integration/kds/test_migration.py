from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from migrations.kds_v1 import TABELAS, downgrade, upgrade


def test_migration_kds_upgrade_downgrade_em_sqlite_memoria():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    existentes = set(inspect(engine).get_table_names())
    assert set(TABELAS) <= existentes
    downgrade(engine)
    restantes = set(inspect(engine).get_table_names())
    assert not (set(TABELAS) & restantes)


def test_migration_kds_recusa_banco_real(tmp_path):
    real = tmp_path / "banco_erp_local.db"
    engine = create_engine(f"sqlite+pysqlite:///{real}")
    with pytest.raises(RuntimeError, match="efemero/teste"):
        upgrade(engine)
    assert not Path(real).exists()


def test_migration_kds_recusa_sqlite_sem_marcador_de_teste(tmp_path):
    comum = tmp_path / "operacao.db"
    engine = create_engine(f"sqlite+pysqlite:///{comum}")
    with pytest.raises(RuntimeError, match="efemero/teste"):
        upgrade(engine)
    assert not Path(comum).exists()
