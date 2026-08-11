"""Seed determinístico do E2E da Expedição e Entrega V1."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1" or os.environ.get("FM_AI_ENTREGA_V1") != "1":
    raise RuntimeError("Seed Entrega so pode executar no E2E isolado")

from core.entrega.modelos_orm import EntregaORM
from core.entrega.runtime_teste import preparar_schema_teste
from core.pagamentos.modelos_orm import ObrigacaoPagamentoORM, PagamentoORM

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR obrigatorio")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Entrega fora da raiz temporaria")

TMPDIR.mkdir(parents=True, exist_ok=True)
if DB_PATH.exists():
    DB_PATH.unlink()
engine = create_engine(f"sqlite+pysqlite:///{DB_PATH.as_posix()}")
preparar_schema_teste(engine)

AGORA = datetime(2026, 8, 11, 15, 0, tzinfo=timezone.utc)


def entrega(
    entrega_id: str,
    pedido_id: str,
    status: str,
    *,
    entregador_id: str | None = None,
    pronta: bool = False,
    checklist: bool = False,
) -> EntregaORM:
    return EntregaORM(
        id=entrega_id,
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        pedido_id=pedido_id,
        endereco_id=f"endereco-{pedido_id}",
        modalidade="propria",
        status=status,
        versao=1,
        tentativa=1,
        entregador_id=entregador_id,
        producao_pronta_em=AGORA if pronta else None,
        checklist_concluido_em=AGORA if checklist else None,
        atribuida_em=AGORA if entregador_id else None,
        coletada_em=None,
        saiu_em=None,
        entregue_em=None,
        prova_entrega_ref=None,
        atualizado_em=AGORA,
    )


def pagamento(pedido_id: str, status: str, *, posterior: bool = False):
    pagamento_id = f"pag-{pedido_id}"
    obrigacao = ObrigacaoPagamentoORM(
        id=pagamento_id,
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        pedido_id=pedido_id,
        comanda_id=None,
        valor_previsto="35.00",
        moeda="BRL",
        criado_em=AGORA,
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"obrigacao-{pedido_id}",
        request_hash=f"hash-obrigacao-{pedido_id}",
    )
    pago = status == "pago"
    row = PagamentoORM(
        id=pagamento_id,
        tenant_id="tenant-e2e",
        unidade_id="unidade-e2e",
        pedido_id=pedido_id,
        comanda_id=None,
        status=status,
        metodo="dinheiro",
        valor_previsto="35.00",
        valor_pago="35.00" if pago else "0.00",
        valor_estornado="0.00",
        saldo="0.00" if pago else "35.00",
        moeda="BRL",
        recebimento_posterior=posterior,
        provedor=None,
        criado_em=AGORA,
        atualizado_em=AGORA,
        versao=1,
        correlation_id=f"corr-{pedido_id}",
        idempotency_key=f"pagamento-{pedido_id}",
        request_hash=f"hash-pagamento-{pedido_id}",
    )
    return obrigacao, row


with Session(engine) as session:
    session.add(
        entrega(
            "entrega-exp",
            "pedido-exp",
            "aguardando_expedicao",
            pronta=True,
        )
    )
    session.add(
        entrega(
            "entrega-paid",
            "pedido-paid",
            "atribuida",
            entregador_id="driver-1",
            pronta=True,
            checklist=True,
        )
    )
    session.add(
        entrega(
            "entrega-pending",
            "pedido-pending",
            "atribuida",
            entregador_id="driver-1",
            pronta=True,
            checklist=True,
        )
    )
    for pedido_id, status in (("pedido-paid", "pago"), ("pedido-pending", "aguardando_entrega")):
        obrigacao, row = pagamento(pedido_id, status)
        session.add(obrigacao)
        session.add(row)
    session.commit()

print(DB_PATH)
