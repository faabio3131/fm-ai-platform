from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from application.crm_cashback_transacoes import (
    CashbackPDVInvalido,
    aplicar_cashback_pdv_em_transacao,
)
from core.crm.cashback import ServicoCashback
from core.dominio.dinheiro import Dinheiro
from core.pdv.modelos import EntradaPDV
from infra.crm.cliente_legado_schema import crm_cliente_legado_v1
from infra.legacy_schema import clientes
from infra.transacoes.uow import RecursosTransacionaisV1
from migrations.crm_cashback_ledger_v1 import upgrade_crm_cashback_ledger_v1
from migrations.crm_cliente_legado_mapping_v1 import (
    upgrade_crm_cliente_legado_mapping_v1,
)
from migrations.crm_clientes_persistencia_v1 import upgrade_crm_clientes_persistencia_v1

TENANT = "tenant-f13b"
UNIDADE = "unidade-f13b"
CLIENTE = "cliente-canonico-f13b"
LEGACY_ID = 81
AGORA = datetime(2026, 9, 5, 21, 0, tzinfo=timezone.utc)


def _engine(*, saldo_legado: Decimal = Decimal("0.00"), mapping: bool = True):
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
                nome="Cliente F13-B",
                whatsapp="5511999990000",
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
                    criado_por="teste-f13b",
                    correlation_id="corr-f13b",
                    criado_em=AGORA,
                )
            )
    return engine


def _entrada(*, usar: bool = False, desconto: str = "0.00") -> EntradaPDV:
    return EntradaPDV(
        produto_id=1,
        produto_nome="Produto",
        quantidade=1,
        preco_unitario=Dinheiro(Decimal("100.00")),
        custo_total=Dinheiro(Decimal("20.00")),
        forma_pagamento="Dinheiro Em Espécie",
        terminal_id="terminal-f13b",
        checkout_id="checkout-f13b",
        cliente_id=LEGACY_ID,
        usar_cashback=usar,
        desconto_cashback=Dinheiro(Decimal(desconto)),
    )


def test_compra_credita_ledger_canonico_sem_usar_saldo_legado() -> None:
    engine = _engine()
    with Session(engine) as session, session.begin():
        recursos = RecursosTransacionaisV1(session)
        resultado = aplicar_cashback_pdv_em_transacao(
            recursos=recursos,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-1",
            entrada=_entrada(),
            timestamp=AGORA,
        )

        assert resultado is not None
        assert resultado.cliente_id == CLIENTE
        assert resultado.cashback_usado == Decimal("0.00")
        assert resultado.cashback_ganho == Decimal("5.00")
        assert resultado.saldo == Decimal("5.00")
        assert len(
            recursos.cashback.historico(
                tenant_id=TENANT, unidade_id=UNIDADE, cliente_id=CLIENTE
            )
        ) == 1


def test_resgate_e_ganho_sao_atomicos_e_replay_nao_duplica() -> None:
    engine = _engine(saldo_legado=Decimal("10.00"))
    with Session(engine) as session, session.begin():
        recursos = RecursosTransacionaisV1(session)
        ServicoCashback(recursos.cashback).creditar(
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            cliente_id=CLIENTE,
            valor=Decimal("10.00"),
            origem="regularizacao_governada",
            referencia="regularizacao://f13b",
            idempotency_key="regularizacao-f13b",
            ocorrido_em=AGORA,
        )
        entrada = _entrada(usar=True, desconto="7.00")

        primeiro = aplicar_cashback_pdv_em_transacao(
            recursos=recursos,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-2",
            entrada=entrada,
            timestamp=AGORA,
        )
        replay = aplicar_cashback_pdv_em_transacao(
            recursos=recursos,
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-2",
            entrada=entrada,
            timestamp=AGORA,
        )

        assert primeiro is not None and replay is not None
        assert primeiro.cashback_usado == Decimal("7.00")
        assert primeiro.cashback_ganho == Decimal("4.65")
        assert primeiro.saldo == Decimal("7.65")
        assert replay.saldo == Decimal("7.65")
        assert len(
            recursos.cashback.historico(
                tenant_id=TENANT, unidade_id=UNIDADE, cliente_id=CLIENTE
            )
        ) == 3


def test_sem_mapping_crm_falha_fechado() -> None:
    engine = _engine(mapping=False)
    with (
        Session(engine) as session,
        session.begin(),
        pytest.raises(CashbackPDVInvalido, match="cliente_legado_sem_mapping_crm"),
    ):
        aplicar_cashback_pdv_em_transacao(
            recursos=RecursosTransacionaisV1(session),
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            pedido_id="pedido-3",
            entrada=_entrada(),
            timestamp=AGORA,
        )


def test_saldo_legado_sem_regularizacao_nao_vira_fallback() -> None:
    engine = _engine(saldo_legado=Decimal("12.00"))
    with Session(engine) as session, session.begin():
        recursos = RecursosTransacionaisV1(session)
        with pytest.raises(
            CashbackPDVInvalido, match="cashback_legacy_regularizacao_pendente"
        ):
            aplicar_cashback_pdv_em_transacao(
                recursos=recursos,
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id="pedido-4",
                entrada=_entrada(usar=True, desconto="5.00"),
                timestamp=AGORA,
            )
        assert recursos.cashback.historico(
            tenant_id=TENANT, unidade_id=UNIDADE, cliente_id=CLIENTE
        ) == ()
