from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session, sessionmaker

from application.crm_cashback_comercial import (
    CashbackComercialInvalido,
    consultar_saldo_cashback_legado,
    creditar_cashback_manual,
)
from core.crm.cashback import ServicoCashback
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.legacy_schema import clientes
from infra.transacoes.uow import RecursosTransacionaisV1
from migrations.crm_cashback_ledger_v1 import upgrade_crm_cashback_ledger_v1
from migrations.crm_cliente_legado_mapping_v1 import (
    upgrade_crm_cliente_legado_mapping_v1,
)
from migrations.crm_clientes_persistencia_v1 import upgrade_crm_clientes_persistencia_v1

TENANT = "tenant-f13c"
UNIDADE = "unidade-f13c"
CLIENTE = "cliente-canonico-f13c"
LEGACY_ID = 91
AGORA = datetime(2026, 9, 6, 1, 0, tzinfo=timezone.utc)


def _fabrica(*, saldo_legado: Decimal = Decimal("0.00"), mapping: bool = True):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        clientes.create(connection, checkfirst=True)
        upgrade_crm_clientes_persistencia_v1(connection)
        upgrade_crm_cliente_legado_mapping_v1(connection)
        upgrade_crm_cashback_ledger_v1(connection)
        connection.execute(
            insert(clientes).values(
                id=LEGACY_ID,
                nome="Cliente F13-C",
                whatsapp="5511999990001",
                total_gasto=0.0,
                saldo_cashback=float(saldo_legado),
                status="Ativo",
            )
        )
        connection.exec_driver_sql(
            """
            INSERT INTO crm_clientes_v1
                (tenant_id, unidade_id, cliente_id, origem, marketplace_origem,
                 criado_em, versao)
            VALUES (?, ?, ?, 'manual', NULL, ?, 1)
            """,
            (TENANT, UNIDADE, CLIENTE, AGORA.replace(tzinfo=None)),
        )
        if mapping:
            connection.execute(
                insert(crm_cliente_legado_v1).values(
                    tenant_id=TENANT,
                    unidade_id=UNIDADE,
                    legacy_cliente_id=LEGACY_ID,
                    cliente_id=CLIENTE,
                    criado_por="teste-f13c",
                    correlation_id="corr-f13c",
                    criado_em=AGORA,
                )
            )
    return engine, sessionmaker(bind=engine, future=True)


def test_consulta_saldo_usa_ledger_e_nao_coluna_legada() -> None:
    engine, fabrica = _fabrica()
    with Session(engine) as session, session.begin():
        recursos = RecursosTransacionaisV1(session)
        ServicoCashback(recursos.cashback).creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("17.50"),
            origem="regularizacao_governada",
            referencia="regularizacao://f13c",
            idempotency_key="regularizacao-f13c",
            ocorrido_em=AGORA,
        )
        session.execute(
            clientes.update()
            .where(clientes.c.id == LEGACY_ID)
            .values(saldo_cashback=999.0)
        )

    resultado = consultar_saldo_cashback_legado(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        legacy_cliente_id=LEGACY_ID,
    )
    assert resultado.cliente_id == CLIENTE
    assert resultado.saldo == Decimal("17.50")


def test_credito_manual_e_atomico_e_legado_e_so_projecao() -> None:
    engine, fabrica = _fabrica()
    primeiro = creditar_cashback_manual(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        legacy_cliente_id=LEGACY_ID,
        valor=Decimal("12.30"),
        referencia="crm-ui://bonus-vip",
        idempotency_key="f13c-manual-1",
    )
    replay = creditar_cashback_manual(
        session_factory=fabrica,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        legacy_cliente_id=LEGACY_ID,
        valor=Decimal("12.30"),
        referencia="crm-ui://bonus-vip",
        idempotency_key="f13c-manual-1",
    )

    assert primeiro.saldo == Decimal("12.30")
    assert replay.saldo == Decimal("12.30")
    with Session(engine) as session:
        recursos = RecursosTransacionaisV1(session)
        assert recursos.cashback.saldo(
            tenant_id=TENANT, unidade_id=UNIDADE, cliente_id=CLIENTE
        ) == Decimal("12.30")
        assert len(
            recursos.cashback.historico(
                tenant_id=TENANT, unidade_id=UNIDADE, cliente_id=CLIENTE
            )
        ) == 1
        saldo_legado = session.scalar(
            select(clientes.c.saldo_cashback).where(clientes.c.id == LEGACY_ID)
        )
        assert Decimal(str(saldo_legado)) == Decimal("12.3")


def test_credito_manual_sem_mapping_falha_fechado() -> None:
    _, fabrica = _fabrica(mapping=False)
    with pytest.raises(
        CashbackComercialInvalido, match="cliente_legado_sem_mapping_crm"
    ):
        creditar_cashback_manual(
            session_factory=fabrica,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            legacy_cliente_id=LEGACY_ID,
            valor=Decimal("10.00"),
            referencia="crm-ui://bonus",
            idempotency_key="f13c-sem-mapping",
        )


def test_saldo_legado_nao_regularizado_nunca_vira_fallback() -> None:
    _, fabrica = _fabrica(saldo_legado=Decimal("25.00"))
    with pytest.raises(
        CashbackComercialInvalido, match="cashback_legacy_regularizacao_pendente"
    ):
        consultar_saldo_cashback_legado(
            session_factory=fabrica,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            legacy_cliente_id=LEGACY_ID,
        )
