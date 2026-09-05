# ruff: noqa: E402
"""Entrypoint Streamlit isolado da superfície comercial Delivery F11-E."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

if os.environ.get("FM_AI_TEST_MODE") != "1":
    raise RuntimeError("app_delivery.py e exclusivo do E2E isolado")
if os.environ.get("FM_AI_DELIVERY_V1") != "1":
    raise RuntimeError("Delivery E2E requer FM_AI_DELIVERY_V1=1")

import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.delivery.ui_streamlit import render_delivery_v1
from core.seguranca.autenticacao import IdentidadeUsuario
from core.seguranca.permissoes import Papel

TMPDIR_RAW = os.environ.get("FM_AI_TEST_TMPDIR")
if not TMPDIR_RAW:
    raise RuntimeError("FM_AI_TEST_TMPDIR e obrigatorio no E2E Delivery")

TMPDIR = Path(TMPDIR_RAW).resolve()
DB_PATH = (TMPDIR / "fm_ai_test.sqlite3").resolve()
REAL_DB = (ROOT / "banco_erp_local.db").resolve()
ALLOWED_ROOT = (ROOT / ".tmp" / "fm-ai-playwright").resolve()
if DB_PATH == REAL_DB or ALLOWED_ROOT not in DB_PATH.parents:
    raise RuntimeError("Banco E2E Delivery fora do diretorio temporario permitido")
if not DB_PATH.exists():
    raise RuntimeError("Banco E2E Delivery nao foi inicializado pelo globalSetup")

engine = create_engine(
    f"sqlite+pysqlite:///{DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)

identidade = IdentidadeUsuario(
    usuario_id="admin-delivery-e2e",
    email="admin-delivery-e2e@example.invalid",
    senha_hash="hash-test-delivery-e2e",
    tenant_id="tenant-delivery-e2e",
    unidade_id="unidade-delivery-e2e",
    papeis=frozenset({Papel.ADMINISTRADOR}),
    unidades_permitidas=frozenset({"unidade-delivery-e2e"}),
    ativo=True,
)

st.set_page_config(page_title="Delivery Próprio — F11-E E2E", layout="wide")
st.session_state["_fm_ai_e2e_run"] = int(
    st.session_state.get("_fm_ai_e2e_run", 0)
) + 1
st.caption("Delivery comercial F11-E E2E pronto")

render_delivery_v1(
    session_factory=SessionLocal,
    identidade=identidade,
)

st.markdown(
    f'<span data-fm-ai-e2e-ready="true" '
    f'data-fm-ai-e2e-run="{st.session_state["_fm_ai_e2e_run"]}" '
    'style="display:none" aria-hidden="true"></span>',
    unsafe_allow_html=True,
)
