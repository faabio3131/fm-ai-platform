# ruff: noqa: E402
"""Entrypoint Streamlit mínimo e exclusivo do E2E da Central de Pedidos."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("app_order_center.py é exclusivo do modo E2E isolado")
if os.environ.get("FM_AI_ORDER_CENTER_V1") != "1":
    raise RuntimeError("Central E2E requer FM_AI_ORDER_CENTER_V1=1")

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.central_pedidos import contexto_central_teste
from core.central_pedidos.ui_streamlit import render_central_pedidos

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR é obrigatório no E2E da Central")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()

if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E da Central fora do diretório temporário permitido")
if not DB_PATH.exists():
    raise RuntimeError("Banco E2E da Central não foi inicializado pelo globalSetup")

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

st.set_page_config(
    page_title="F&M AI FOOD — Central E2E",
    page_icon="📋",
    layout="wide",
)

st.caption("Central E2E pronta")
render_central_pedidos(
    engine=engine,
    session_factory=SessionLocal,
    contexto=contexto_central_teste(
        correlation_id=str(uuid4()),
        solicitado_em=datetime.now(timezone.utc),
    ),
)
