# ruff: noqa: E402
"""Entrypoint Streamlit minimo e exclusivo do E2E Salao."""

import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("app_salao.py e exclusivo do modo E2E isolado")
if os.environ.get("FM_AI_SALAO_V1") != "1":
    raise RuntimeError("Salao E2E requer FM_AI_SALAO_V1=1")

import streamlit as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from core.pagamentos.modelos_orm import PagamentoORM
from core.salao.modelos import StatusComanda
from core.salao.modelos_orm import ComandaORM, PedidoComandaORM
from core.salao.runtime_teste import (
    contexto_salao_teste,
    preparar_schema_teste,
    registrar_pagamento_confirmado_teste,
)
from core.salao.ui_streamlit import render_salao

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no E2E Salao")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()

if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Salao fora do diretorio temporario permitido")
if not DB_PATH.exists():
    raise RuntimeError("Banco E2E Salao nao foi inicializado pelo globalSetup")

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

st.set_page_config(
    page_title="F&M AI FOOD — Salao E2E",
    page_icon="🪑",
    layout="wide",
)

st.session_state["_fm_ai_e2e_run"] = int(
    st.session_state.get("_fm_ai_e2e_run", 0)
) + 1

st.caption("Salao E2E pronto")
preparar_schema_teste(engine)
contexto = contexto_salao_teste(
    correlation_id="corr-salao-e2e-ui",
    solicitado_em=datetime.now(timezone.utc),
    papel="gerente",
)

with SessionLocal() as session:
    comanda = session.scalar(
        select(ComandaORM).where(
            ComandaORM.tenant_id == contexto.tenant_id,
            ComandaORM.unidade_id == contexto.unidade_id,
            ComandaORM.total == Decimal("70.00"),
            ComandaORM.status.notin_(
                [StatusComanda.FECHADA.value, StatusComanda.CANCELADA.value]
            ),
        )
    )
    if comanda is not None:
        pedido = session.scalar(
            select(PedidoComandaORM).where(
                PedidoComandaORM.tenant_id == contexto.tenant_id,
                PedidoComandaORM.unidade_id == contexto.unidade_id,
                PedidoComandaORM.comanda_id == comanda.id,
            )
        )
        if pedido is not None:
            pagamentos = (
                ("e2e-pay-pix", "pix", Decimal("40.00")),
                ("e2e-pay-cash", "dinheiro", Decimal("30.00")),
            )
            for pagamento_id, metodo, valor in pagamentos:
                if (
                    session.get(
                        PagamentoORM,
                        (pagamento_id, contexto.tenant_id, contexto.unidade_id),
                    )
                    is None
                ):
                    registrar_pagamento_confirmado_teste(
                        session,
                        pagamento_id=pagamento_id,
                        pedido_id=pedido.pedido_id,
                        comanda_id=comanda.id,
                        metodo=metodo,
                        valor=valor,
                        agora=datetime.now(timezone.utc),
                    )
            session.commit()

render_salao(
    engine=engine,
    session_factory=SessionLocal,
    contexto=contexto,
)

st.markdown(
    f'<span data-fm-ai-e2e-ready="true" '
    f'data-fm-ai-e2e-run="{st.session_state["_fm_ai_e2e_run"]}" '
    'style="display:none" aria-hidden="true"></span>',
    unsafe_allow_html=True,
)
