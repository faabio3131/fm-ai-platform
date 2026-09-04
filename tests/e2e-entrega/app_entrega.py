"""Entrypoint Streamlit mínimo e exclusivo do E2E da PR13."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("app_entrega.py e exclusivo do E2E")
if os.environ.get("FM_AI_ENTREGA_V1") != "1":
    raise RuntimeError("Entrega E2E requer FM_AI_ENTREGA_V1=1")

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.entrega.runtime_teste import contexto_entrega_teste
from core.entrega.ui_streamlit import render_entrega

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Entrega fora do diretorio permitido")
if not DB_PATH.exists():
    raise RuntimeError("Banco E2E Entrega nao inicializado")

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

st.set_page_config(page_title="F&M AI FOOD — Entrega E2E", page_icon="🛵", layout="wide")
st.session_state["_fm_ai_e2e_run"] = int(st.session_state.get("_fm_ai_e2e_run", 0)) + 1

papel = str(st.query_params.get("papel", "expedicao"))
if papel not in {"expedicao", "entregador", "gerente"}:
    papel = "expedicao"
usuario_id = "driver-1" if papel == "entregador" else f"{papel}-e2e"
contexto = contexto_entrega_teste(
    correlation_id=f"entrega-ui-{papel}-{usuario_id}",
    solicitado_em=datetime.now(timezone.utc),
    papel=papel,
    usuario_id=usuario_id,
)

st.caption("Entrega E2E pronta")
render_entrega(session_factory=SessionLocal, contexto=contexto)
st.markdown(
    f'<span data-fm-ai-e2e-ready="true" '
    f'data-fm-ai-e2e-run="{st.session_state["_fm_ai_e2e_run"]}" '
    f'data-fm-ai-e2e-papel="{papel}" '
    'style="display:none" aria-hidden="true"></span>',
    unsafe_allow_html=True,
)
