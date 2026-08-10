# ruff: noqa: E402
"""Seed isolado da Central: canary PR8, shadow e Venda legada pura."""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
    VendaFinanceiraORM,
)
from core.pdv.modelos_orm import PDVBase, ReconciliacaoPDVORM, VendaLegadaLinkORM
from core.pedidos.modelos_orm import (
    AdicionalItemPedidoORM,
    EventoPedidoPersistidoORM,
    ItemPedidoORM,
    ObservacaoPedidoORM,
    OrdersBase,
    PedidoORM,
)

db = Path(os.environ["FM_AI_TEST_TMPDIR"]) / "fm_ai_test.sqlite3"
real = ROOT / "banco_erp_local.db"
if db.resolve() == real.resolve() or os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("Seed da Central fora do ambiente isolado")

engine = create_engine(f"sqlite:///{db}")
OrdersBase.metadata.create_all(engine)
PaymentsBase.metadata.create_all(engine)
PDVBase.metadata.create_all(engine)
now = datetime.now(timezone.utc).replace(microsecond=0)

with Session(engine) as session:
    canary = PedidoORM(
        id="pedido-canary-pr8",
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        origem="balcao",
        canal="presencial",
        status="rascunho",
        cliente_id=None,
        criado_em=now,
        atualizado_em=now,
        versao=1,
        correlation_id="corr-canary",
        idempotency_key="pedido-canary",
        request_hash="hash",
        subtotal=Decimal("24.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("24.00"),
    )
    item = ItemPedidoORM(
        id="item-canary",
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        pedido_id=canary.id,
        ordem=0,
        produto_id="legacy:produto:1",
        nome_produto="Burger Canary PR8",
        quantidade=1,
        preco_unitario=Decimal("22.00"),
        subtotal=Decimal("24.00"),
        observacao="Sem cebola",
        ficha_versao="v1",
    )
    item.adicionais = [
        AdicionalItemPedidoORM(
            id="adicional-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            item_id=item.id,
            ordem=0,
            nome="Queijo extra",
            quantidade=1,
            preco_unitario=Decimal("2.00"),
            subtotal=Decimal("2.00"),
        )
    ]
    canary.itens = [item]
    canary.observacoes = [
        ObservacaoPedidoORM(
            id="obs-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            ordem=0,
            texto="Retirada no balcão",
            criado_em=now,
        )
    ]
    shadow = PedidoORM(
        id="pedido-shadow-pr8",
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        origem="balcao",
        canal="whatsapp",
        status="rascunho",
        cliente_id=None,
        criado_em=now,
        atualizado_em=now,
        versao=1,
        correlation_id="corr-shadow",
        idempotency_key="pedido-shadow",
        request_hash="hash",
        subtotal=Decimal("10.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("10.00"),
    )
    session.add_all([canary, shadow])
    session.flush()
    session.add(
        EventoPedidoPersistidoORM(
            event_id="evento-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            event_type="pedido.criado",
            correlation_id="corr-canary",
            causation_id=None,
            idempotency_key="evento-canary",
            occurred_at=now,
            payload={"resumo": "seguro"},
            version=1,
        )
    )
    session.add(
        ObrigacaoPagamentoORM(
            id="pagamento-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            comanda_id=None,
            valor_previsto=Decimal("24.00"),
            moeda="BRL",
            criado_em=now,
            versao=1,
            correlation_id="corr-canary",
            idempotency_key="obrigacao-canary",
            request_hash="hash",
        )
    )
    session.add(
        PagamentoORM(
            id="pagamento-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            comanda_id=None,
            status="pago",
            metodo="dinheiro",
            valor_previsto=Decimal("24.00"),
            valor_pago=Decimal("24.00"),
            valor_estornado=Decimal("0.00"),
            saldo=Decimal("0.00"),
            moeda="BRL",
            recebimento_posterior=False,
            provedor=None,
            criado_em=now,
            atualizado_em=now,
            versao=1,
            correlation_id="corr-canary",
            idempotency_key="pagamento-canary",
            request_hash="hash",
        )
    )
    session.add(
        VendaFinanceiraORM(
            id="venda-financeira-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            pagamento_id="pagamento-canary",
            comanda_id=None,
            criterio_codigo="pagamento_confirmado",
            criterio_versao=1,
            valor=Decimal("24.00"),
            moeda="BRL",
            metodo="dinheiro",
            reconhecida_em=now,
            correlation_id="corr-canary",
            idempotency_key="vf-canary",
            request_hash="hash",
        )
    )
    session.add(
        VendaLegadaLinkORM(
            id="link-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=canary.id,
            venda_financeira_id="venda-financeira-canary",
            venda_legada_id="1",
            criado_em=now,
        )
    )
    session.add(
        ReconciliacaoPDVORM(
            id="reconciliacao-canary",
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            modo="AUTHORITATIVE_CANARY",
            pedido_id=canary.id,
            pagamento_id="pagamento-canary",
            venda_financeira_id="venda-financeira-canary",
            venda_legada_id="1",
            idempotency_key="reconciliacao-canary",
            valor_pedido=Decimal("24.00"),
            valor_pagamento=Decimal("24.00"),
            valor_venda_financeira=Decimal("24.00"),
            valor_venda_legada=Decimal("29.90"),
            estoque_estrategia="legado",
            cashback_usado=Decimal("0.00"),
            cashback_ganho=Decimal("0.00"),
            status="conciliado",
            divergencias=[],
            criado_em=now,
        )
    )
    session.commit()
