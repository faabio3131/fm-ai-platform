"""Seed isolado da interface do garçom V1 com duas alçadas e avisos prontos."""

import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from core.kds.modelos_orm import KDSBase, ProducaoItemORM, SetorProducaoORM
from core.pedidos.modelos_orm import ItemPedidoORM, OrdersBase, PedidoORM
from core.salao.modelos_orm import (
    ComandaORM,
    MesaORM,
    PedidoComandaORM,
    SalaoBase,
)

if os.environ.get("FM_AI_TEST_MODE") != "1" or os.environ.get("FM_AI_GARCOM_V1") != "1":
    raise RuntimeError("Seed Garcom exige modo E2E isolado e flag Garcom")

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no seed Garcom")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Garcom fora do diretorio temporario permitido")

engine = create_engine(f"sqlite+pysqlite:///{DB_PATH.as_posix()}")
OrdersBase.metadata.create_all(engine, checkfirst=True)
SalaoBase.metadata.drop_all(engine, checkfirst=True)
KDSBase.metadata.drop_all(engine, checkfirst=True)
SalaoBase.metadata.create_all(engine, checkfirst=True)
KDSBase.metadata.create_all(engine, checkfirst=True)

now = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "tenant-e2e"
UNIDADE = "unidade-e2e"


def pedido(pedido_id: str, item_id: str, nome: str) -> tuple[PedidoORM, ItemPedidoORM]:
    cabecalho = PedidoORM(
        id=pedido_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="pdv",
        canal="salao",
        status="enviado_producao",
        cliente_id=None,
        criado_em=now - timedelta(minutes=12),
        atualizado_em=now - timedelta(minutes=5),
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"pedido-{pedido_id}",
        request_hash=f"hash-{pedido_id}",
        subtotal=Decimal("30.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("30.00"),
    )
    item = ItemPedidoORM(
        id=item_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        pedido_id=pedido_id,
        ordem=1,
        produto_id=f"produto-{item_id}",
        nome_produto=nome,
        quantidade=1,
        preco_unitario=Decimal("30.00"),
        subtotal=Decimal("30.00"),
        observacao=None,
        ficha_versao="v1",
    )
    cabecalho.itens = [item]
    return cabecalho, item


with Session(engine) as session:
    ids_pedido = ("pedido-garcom-1", "pedido-garcom-2")
    ids_item = ("item-garcom-1", "item-garcom-2")
    session.execute(
        delete(ItemPedidoORM).where(
            ItemPedidoORM.tenant_id == TENANT,
            ItemPedidoORM.unidade_id == UNIDADE,
            ItemPedidoORM.id.in_(ids_item),
        )
    )
    session.execute(
        delete(PedidoORM).where(
            PedidoORM.tenant_id == TENANT,
            PedidoORM.unidade_id == UNIDADE,
            PedidoORM.id.in_(ids_pedido),
        )
    )

    p1, i1 = pedido("pedido-garcom-1", "item-garcom-1", "Burger da Mesa 01")
    p2, i2 = pedido("pedido-garcom-2", "item-garcom-2", "Massa da Mesa 02")
    session.add_all([p1, p2])
    session.flush()

    session.add_all(
        [
            MesaORM(
                id="mesa-garcom-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="01",
                nome="Janela",
                capacidade=4,
                status="ocupada",
                ativo=True,
                versao=2,
                criado_em=now - timedelta(hours=1),
                atualizado_em=now - timedelta(minutes=20),
            ),
            MesaORM(
                id="mesa-garcom-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="02",
                nome="Centro",
                capacidade=4,
                status="ocupada",
                ativo=True,
                versao=2,
                criado_em=now - timedelta(hours=1),
                atualizado_em=now - timedelta(minutes=20),
            ),
            MesaORM(
                id="mesa-garcom-3",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="03",
                nome="Livre",
                capacidade=2,
                status="livre",
                ativo=True,
                versao=1,
                criado_em=now - timedelta(hours=1),
                atualizado_em=now - timedelta(minutes=20),
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            ComandaORM(
                id="comanda-garcom-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                mesa_id="mesa-garcom-1",
                numero="C-001",
                status="em_consumo",
                responsavel_id="garcom-1",
                aberta_em=now - timedelta(minutes=30),
                fechada_em=None,
                total=Decimal("30.00"),
                saldo=Decimal("30.00"),
                recebimento_posterior_autorizado=False,
                versao=2,
            ),
            ComandaORM(
                id="comanda-garcom-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                mesa_id="mesa-garcom-2",
                numero="C-002",
                status="em_consumo",
                responsavel_id="garcom-2",
                aberta_em=now - timedelta(minutes=25),
                fechada_em=None,
                total=Decimal("30.00"),
                saldo=Decimal("30.00"),
                recebimento_posterior_autorizado=False,
                versao=2,
            ),
            PedidoComandaORM(
                id="vinculo-garcom-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                comanda_id="comanda-garcom-1",
                pedido_id=p1.id,
                participante_id=None,
                valor=Decimal("30.00"),
                criado_em=now - timedelta(minutes=20),
            ),
            PedidoComandaORM(
                id="vinculo-garcom-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                comanda_id="comanda-garcom-2",
                pedido_id=p2.id,
                participante_id=None,
                valor=Decimal("30.00"),
                criado_em=now - timedelta(minutes=18),
            ),
        ]
    )

    session.add(
        SetorProducaoORM(
            id="setor-garcom-cozinha",
            tenant_id=TENANT,
            unidade_id=UNIDADE,
            codigo="cozinha",
            nome="Cozinha",
            ordem=1,
            sla_segundos=600,
            ativo=True,
            criado_em=now - timedelta(hours=1),
            atualizado_em=now - timedelta(hours=1),
        )
    )
    session.flush()

    session.add_all(
        [
            ProducaoItemORM(
                id="prod-garcom-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=p1.id,
                pedido_item_id=i1.id,
                setor_id="setor-garcom-cozinha",
                status="pronta",
                prioridade=0,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=4,
                criado_em=now - timedelta(minutes=10),
                atualizado_em=now - timedelta(minutes=2),
                pronta_em=now - timedelta(minutes=2),
                responsavel_id="cozinha-e2e",
                pausa_acumulada_segundos=0,
                idempotency_key="seed-garcom-route-1",
                request_hash="seed-garcom-hash-1",
            ),
            ProducaoItemORM(
                id="prod-garcom-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=p2.id,
                pedido_item_id=i2.id,
                setor_id="setor-garcom-cozinha",
                status="pronta",
                prioridade=0,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=4,
                criado_em=now - timedelta(minutes=9),
                atualizado_em=now - timedelta(minutes=1),
                pronta_em=now - timedelta(minutes=1),
                responsavel_id="cozinha-e2e",
                pausa_acumulada_segundos=0,
                idempotency_key="seed-garcom-route-2",
                request_hash="seed-garcom-hash-2",
            ),
        ]
    )
    session.commit()
