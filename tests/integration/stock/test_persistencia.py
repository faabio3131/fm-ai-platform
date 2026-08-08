from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.estoque.erros import ConcorrenciaEstoque
from core.estoque.modelos import MovimentoEstoque, TipoMovimento
from migrations.stock_v1 import downgrade, upgrade

AGORA = datetime(2026, 1, 1, tzinfo=timezone.utc)


def movimento(
    mid: str,
    chave: str,
    tipo: TipoMovimento = TipoMovimento.ENTRADA,
    quantidade: str = "10",
    versao: int = 1,
) -> MovimentoEstoque:
    return MovimentoEstoque(
        mid,
        "t",
        "u",
        "i",
        tipo,
        Decimal(quantidade),
        "kg",
        "teste",
        mid,
        versao,
        chave,
        AGORA,
        "corr",
        None,
        "ator",
        "teste",
    )


def test_migration_aditiva_roundtrip_indices_e_constraints() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    insp = inspect(engine)
    assert set(
        ("estoque_ledger_v1", "estoque_saldos_v1", "estoque_reservas_v1")
    ) <= set(insp.get_table_names())
    assert {i["name"] for i in insp.get_indexes("estoque_ledger_v1")} >= {
        "ix_estoque_ledger_escopo_insumo_ordem",
        "ix_estoque_ledger_escopo_origem",
    }
    with Session(engine) as session:
        repo = RepositorioLedgerSQLAlchemy(session)
        repo.append(movimento("m1", "k1"))
        session.commit()
        assert repo.consultar_saldo("t", "u", "i").saldo_fisico == 10
        assert repo.listar_movimentos("t", "u", "i")[0].movimento_id == "m1"
    downgrade(engine)
    assert not inspect(engine).get_table_names()


def test_unique_idempotencia_rollback_e_cas() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    with Session(engine) as session:
        repo = RepositorioLedgerSQLAlchemy(session)
        repo.append(movimento("m1", "k1"))
        session.commit()
        with pytest.raises(ConcorrenciaEstoque):
            repo.append(
                movimento("m2", "k2", TipoMovimento.RESERVA, "7", 2), versao_esperada=0
            )
        session.rollback()
        assert repo.consultar_saldo("t", "u", "i").saldo_fisico == 10


def test_migration_recusa_banco_real_ou_nao_marcado_como_teste(tmp_path) -> None:
    for nome in ("banco_erp_local.db", "producao.db"):
        with pytest.raises(RuntimeError):
            upgrade(create_engine(f"sqlite+pysqlite:///{tmp_path / nome}"))
