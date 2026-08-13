# ruff: noqa: E402
"""Seed isolado do KDS V1 com dois setores e duas filas independentes."""

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

if os.environ.get("FM_AI_TEST_MODE") != "1" or os.environ.get("FM_AI_KDS_V1") != "1":
    raise RuntimeError("Seed KDS exige modo E2E isolado e flag KDS")

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no seed KDS")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E KDS fora do diretorio temporario permitido")

engine = create_engine(f"sqlite+pysqlite:///{DB_PATH.as_posix()}")
OrdersBase.metadata.create_all(engine, checkfirst=True)
# O seed pode ser repetido no mesmo workspace: reconstruir somente tabelas KDS.
KDSBase.metadata.drop_all(engine, checkfirst=True)
KDSBase.metadata.create_all(engine, checkfirst=True)

now = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "tenant-e2e"
UNIDADE = "unidade-e2e"


def pedido(pedido_id: str, item_id: str, nome: str, ordem: int) -> tuple[PedidoORM, ItemPedidoORM]:
    cabecalho = PedidoORM(
        id=pedido_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="pdv",
        canal="pdv",
        status="enviado_producao",
        cliente_id=None,
        criado_em=now - timedelta(minutes=2),
        atualizado_em=now - timedelta(minutes=2),
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"pedido-{pedido_id}",
        request_hash=f"hash-{pedido_id}",
        subtotal=Decimal("20.00"),
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=Decimal("20.00"),
    )
    item = ItemPedidoORM(
        id=item_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        pedido_id=pedido_id,
        ordem=ordem,
        produto_id=f"produto-{item_id}",
        nome_produto=nome,
        quantidade=1,
        preco_unitario=Decimal("20.00"),
        subtotal=Decimal("20.00"),
        observacao=None,
        ficha_versao="v1",
    )
    cabecalho.itens = [item]
    return cabecalho, item


with Session(engine) as session:
    ids_pedido = ("pedido-kds-quente", "pedido-kds-bebida")
    ids_item = ("item-kds-quente", "item-kds-bebida")
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

    quente, item_quente = pedido(
        "pedido-kds-quente", "item-kds-quente", "Burger KDS", 0
    )
    bebida, item_bebida = pedido(
        "pedido-kds-bebida", "item-kds-bebida", "Suco KDS", 0
    )
    session.add_all([quente, bebida])
    session.flush()

    session.add_all(
        [
            SetorProducaoORM(
                id="setor-quente",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="quente",
                nome="Cozinha quente",
                ordem=1,
                sla_segundos=600,
                ativo=True,
                criado_em=now - timedelta(minutes=10),
                atualizado_em=now - timedelta(minutes=10),
            ),
            SetorProducaoORM(
                id="setor-bebidas",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="bebidas",
                nome="Bebidas",
                ordem=2,
                sla_segundos=180,
                ativo=True,
                criado_em=now - timedelta(minutes=10),
                atualizado_em=now - timedelta(minutes=10),
            ),
        ]
    )
    session.flush()

    session.add_all(
        [
            ProducaoItemORM(
                id="prod-kds-quente",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=quente.id,
                pedido_item_id=item_quente.id,
                setor_id="setor-quente",
                status="aguardando",
                prioridade=1,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=1,
                criado_em=now - timedelta(seconds=120),
                atualizado_em=now - timedelta(seconds=120),
                responsavel_id=None,
                pausa_acumulada_segundos=0,
                idempotency_key="seed-route-quente",
                request_hash="seed-hash-quente",
            ),
            ProducaoItemORM(
                id="prod-kds-bebida",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                pedido_id=bebida.id,
                pedido_item_id=item_bebida.id,
                setor_id="setor-bebidas",
                status="aguardando",
                prioridade=10,
                quantidade=Decimal("1.0000"),
                tentativa=1,
                versao=1,
                criado_em=now - timedelta(seconds=60),
                atualizado_em=now - timedelta(seconds=60),
                responsavel_id=None,
                pausa_acumulada_segundos=0,
                idempotency_key="seed-route-bebida",
                request_hash="seed-hash-bebida",
            ),
        ]
    )
    session.commit()
