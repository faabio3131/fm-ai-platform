from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import MetaData, Table, create_engine, insert
from sqlalchemy.orm import Session

from core.crm.cashback import ServicoCashback
from core.crm.erros import ErroCRM
from infra.crm.cashback_sqlalchemy import RepositorioCashbackSQLAlchemy
from migrations.crm_cashback_ledger_v1 import upgrade_crm_cashback_ledger_v1
from migrations.crm_clientes_persistencia_v1 import upgrade_crm_clientes_persistencia_v1

TENANT = "tenant-1"
UNIDADE = "unidade-1"
CLIENTE = "cliente-1"
AGORA = datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc)


def _engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        upgrade_crm_clientes_persistencia_v1(connection)
        upgrade_crm_cashback_ledger_v1(connection)
        tabela = Table(
            "crm_clientes_v1",
            MetaData(),
            autoload_with=connection,
        )
        connection.execute(
            insert(tabela).values(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
                origem="manual",
                marketplace_origem=None,
                criado_em=AGORA,
                versao=1,
            )
        )
    return engine


def _servico(session: Session) -> ServicoCashback:
    return ServicoCashback(RepositorioCashbackSQLAlchemy(session))


def test_credito_e_replay_sao_idempotentes() -> None:
    engine = _engine()
    with Session(engine) as session, session.begin():
        servico = _servico(session)
        primeiro = servico.creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("10.00"),
            origem="ajuste_manual",
            referencia="admin://credito-1",
            idempotency_key="credito-1",
            ocorrido_em=AGORA,
        )
        replay = servico.creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("10.00"),
            origem="ajuste_manual",
            referencia="admin://credito-1",
            idempotency_key="credito-1",
            ocorrido_em=AGORA,
        )

        assert primeiro.saldo == Decimal("10.00")
        assert primeiro.idempotente is False
        assert replay.saldo == Decimal("10.00")
        assert replay.idempotente is True
        assert (
            len(
                servico.ledger.historico(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    cliente_id=CLIENTE,
                )
            )
            == 1
        )


def test_reuso_da_idempotencia_com_semantica_diferente_falha() -> None:
    engine = _engine()
    with Session(engine) as session, session.begin():
        servico = _servico(session)
        servico.creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("10.00"),
            origem="ajuste_manual",
            referencia="admin://credito-1",
            idempotency_key="credito-1",
            ocorrido_em=AGORA,
        )

        with pytest.raises(ErroCRM, match="conflito_idempotencia_cashback"):
            servico.creditar(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
                valor=Decimal("11.00"),
                origem="ajuste_manual",
                referencia="admin://credito-1",
                idempotency_key="credito-1",
                ocorrido_em=AGORA,
            )

        assert (
            servico.ledger.saldo(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
            )
            == Decimal("10.00")
        )


def test_debito_nunca_permite_saldo_negativo_e_replay_nao_duplica() -> None:
    engine = _engine()
    with Session(engine) as session, session.begin():
        servico = _servico(session)
        servico.creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("10.00"),
            origem="venda",
            referencia="pedido://1",
            idempotency_key="ganho-1",
            ocorrido_em=AGORA,
        )
        debito = servico.debitar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("7.00"),
            origem="pdv",
            referencia="pedido://2",
            idempotency_key="uso-1",
            ocorrido_em=AGORA,
        )
        replay = servico.debitar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("7.00"),
            origem="pdv",
            referencia="pedido://2",
            idempotency_key="uso-1",
            ocorrido_em=AGORA,
        )

        assert debito.saldo == Decimal("3.00")
        assert replay.idempotente is True
        assert replay.saldo == Decimal("3.00")

        with pytest.raises(ErroCRM, match="cashback_saldo_insuficiente"):
            servico.debitar(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
                valor=Decimal("3.01"),
                origem="pdv",
                referencia="pedido://3",
                idempotency_key="uso-2",
                ocorrido_em=AGORA,
            )

        assert (
            servico.ledger.saldo(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
            )
            == Decimal("3.00")
        )
        assert (
            len(
                servico.ledger.historico(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    cliente_id=CLIENTE,
                )
            )
            == 2
        )


def test_migration_0039_e_idempotente_e_nao_faz_backfill() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        upgrade_crm_clientes_persistencia_v1(connection)
        upgrade_crm_cashback_ledger_v1(connection)
        upgrade_crm_cashback_ledger_v1(connection)

    with Session(engine) as session:
        repo = RepositorioCashbackSQLAlchemy(session)
        assert (
            repo.saldo(
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                cliente_id=CLIENTE,
            )
            == Decimal("0.00")
        )
