"""Página comercial de Integrações e Credenciais do Kordena V1."""

from __future__ import annotations

from dotenv import load_dotenv
import streamlit as st

from core.runtime import build_engine, load_runtime_settings
from infra.seguranca.session_guard import build_session_factory
from infra.streamlit_app.auth_ui import require_authentication, render_identity_sidebar
from infra.streamlit_app.integracoes_admin import render_integracoes_admin
from migrations.runner import assert_schema_current


load_dotenv()
st.set_page_config(
    page_title="Integrações e Credenciais — Kordena",
    page_icon="🔐",
    layout="wide",
)

settings = load_runtime_settings()
engine = build_engine(settings)
session_factory = build_session_factory(engine=engine, commercial=settings.commercial)
if settings.commercial:
    assert_schema_current(engine)

identity = require_authentication(session_factory=session_factory, settings=settings)
with st.sidebar:
    st.subheader("🔐 Acesso Corporativo")
    render_identity_sidebar(identity, settings)

render_integracoes_admin(identidade=identity, session_factory=session_factory)
