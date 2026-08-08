from decimal import Decimal
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from core.pagamentos.modelos_orm import PagamentoORM
from migrations.payments_v1 import TABELAS, downgrade, upgrade


def test_migration_aditiva_roundtrip_constraints_e_rollback() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    upgrade(engine)
    assert set(TABELAS) <= set(inspect(engine).get_table_names())
    with Session(engine) as session:
        agora = datetime(2026, 8, 8, tzinfo=timezone.utc)
        session.add(
            PagamentoORM(
                id="p",
                tenant_id="t",
                unidade_id="u",
                pedido_id="o",
                status="pendente",
                metodo="pix",
                valor_previsto=Decimal("29.90"),
                valor_pago=Decimal("0"),
                valor_estornado=Decimal("0"),
                saldo=Decimal("29.90"),
                moeda="BRL",
                recebimento_posterior=False,
                criado_em=agora,
                atualizado_em=agora,
                versao=1,
                correlation_id="c",
                idempotency_key="i",
                request_hash="h",
            )
        )
        session.commit()
        row = session.get(PagamentoORM, ("p", "t", "u"))
        assert row is not None
        assert Decimal(str(row.valor_previsto)) == Decimal("29.90")
    downgrade(engine)
    assert not (set(TABELAS) & set(inspect(engine).get_table_names()))


def test_migration_recusa_banco_real(tmp_path) -> None:
    with pytest.raises(RuntimeError):
        upgrade(create_engine(f"sqlite+pysqlite:///{tmp_path / 'banco_erp_local.db'}"))
    with pytest.raises(RuntimeError):
        upgrade(create_engine(f"sqlite+pysqlite:///{tmp_path / 'financeiro.db'}"))
