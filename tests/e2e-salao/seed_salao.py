# ruff: noqa: E402
"""Seed isolado da PR11 com mesas livres e dois pedidos de consumo."""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session

from core.pedidos.modelos_orm import OrdersBase, PedidoORM
from core.salao.modelos_orm import MesaORM, SalaoBase

if os.environ.get("FM_AI_TEST_MODE") != "1" or os.environ.get("FM_AI_SALAO_V1") != "1":
    raise RuntimeError("Seed Salao exige modo E2E isolado e flag Salao")

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no seed Salao")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Salao fora do diretorio temporario permitido")

engine = create_engine(f"sqlite+pysqlite:///{DB_PATH.as_posix()}")
OrdersBase.metadata.create_all(engine, checkfirst=True)
SalaoBase.metadata.drop_all(engine, checkfirst=True)
SalaoBase.metadata.create_all(engine, checkfirst=True)

now = datetime.now(timezone.utc).replace(microsecond=0)
TENANT = "tenant-e2e"
UNIDADE = "unidade-e2e"


def novo_pedido(pedido_id: str, total: str) -> PedidoORM:
    valor = Decimal(total)
    return PedidoORM(
        id=pedido_id,
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        origem="salao",
        canal="mesa",
        status="confirmado",
        cliente_id=None,
        criado_em=now,
        atualizado_em=now,
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"seed-{pedido_id}",
        request_hash=f"hash-{pedido_id}",
        subtotal=valor,
        descontos=Decimal("0.00"),
        taxas=Decimal("0.00"),
        total=valor,
    )


with Session(engine) as session:
    session.execute(
        delete(PedidoORM).where(
            PedidoORM.tenant_id == TENANT,
            PedidoORM.unidade_id == UNIDADE,
            PedidoORM.id.in_(("pedido-salao-1", "pedido-salao-2")),
        )
    )
    session.add_all(
        [
            novo_pedido("pedido-salao-1", "40.00"),
            novo_pedido("pedido-salao-2", "30.00"),
            MesaORM(
                id="mesa-salao-1",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="01",
                nome="Janela",
                capacidade=4,
                status="livre",
                posicao_x=Decimal("1.00"),
                posicao_y=Decimal("1.00"),
                ativo=True,
                versao=1,
                criado_em=now,
                atualizado_em=now,
            ),
            MesaORM(
                id="mesa-salao-2",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="02",
                nome="Centro",
                capacidade=4,
                status="livre",
                posicao_x=Decimal("2.00"),
                posicao_y=Decimal("1.00"),
                ativo=True,
                versao=1,
                criado_em=now,
                atualizado_em=now,
            ),
            MesaORM(
                id="mesa-salao-3",
                tenant_id=TENANT,
                unidade_id=UNIDADE,
                codigo="03",
                nome="Fundo",
                capacidade=6,
                status="livre",
                posicao_x=Decimal("3.00"),
                posicao_y=Decimal("1.00"),
                ativo=True,
                versao=1,
                criado_em=now,
                atualizado_em=now,
            ),
        ]
    )
    session.commit()
