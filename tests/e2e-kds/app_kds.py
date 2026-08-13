# ruff: noqa: E402
"""Entrypoint Streamlit minimo e exclusivo do E2E KDS."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("app_kds.py e exclusivo do modo E2E isolado")
if os.environ.get("FM_AI_KDS_V1") != "1":
    raise RuntimeError("KDS E2E requer FM_AI_KDS_V1=1")

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.kds import contexto_kds_teste
from core.kds.ui_streamlit import render_kds

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no E2E KDS")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()

if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E KDS fora do diretorio temporario permitido")
if not DB_PATH.exists():
    raise RuntimeError("Banco E2E KDS nao foi inicializado pelo globalSetup")

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

st.set_page_config(
    page_title="F&M AI FOOD — KDS E2E",
    page_icon="🍳",
    layout="wide",
)

st.session_state["_fm_ai_e2e_run"] = int(
    st.session_state.get("_fm_ai_e2e_run", 0)
) + 1

st.caption("KDS E2E pronto")
render_kds(
    engine=engine,
    session_factory=SessionLocal,
    permitir_simulacao_offline=True,
    contexto=contexto_kds_teste(
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
        papel="administrador",
    ),
)

st.markdown(
    f'<span data-fm-ai-e2e-ready="true" '
    f'data-fm-ai-e2e-run="{st.session_state["_fm_ai_e2e_run"]}" '
    'style="display:none" aria-hidden="true"></span>',
    unsafe_allow_html=True,
)
