"""Entrada protegida da área Administração / Proprietário do Kordena V1."""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from core.runtime import build_engine, load_runtime_settings
from infra.seguranca.session_guard import build_session_factory
from infra.streamlit_app.admin_proprietario import render_admin_proprietario
from infra.streamlit_app.auth_ui import (
    render_identity_sidebar,
    require_authentication,
    require_sensitive_reauthentication,
)
from infra.streamlit_app.sensitive_idle_watchdog import (
    render_sensitive_idle_watchdog,
)
from migrations.runner import assert_schema_current

load_dotenv()
st.set_page_config(
    page_title="Administração / Proprietário — Kordena",
    page_icon="🔐",
    layout="wide",
)

settings = load_runtime_settings()
engine = build_engine(settings)
session_factory = build_session_factory(engine=engine, commercial=settings.commercial)
if settings.commercial:
    assert_schema_current(engine)

identity = require_authentication(session_factory=session_factory, settings=settings)
require_sensitive_reauthentication(
    identity=identity,
    session_factory=session_factory,
    settings=settings,
)
render_sensitive_idle_watchdog(identity)

with st.sidebar:
    st.subheader("🔐 Acesso Corporativo")
    render_identity_sidebar(identity, settings)

st.title("🔐 Administração / Proprietário")
st.caption(
    "Área administrativa protegida do estabelecimento. O acesso exige o PIN "
    "administrativo individual, separado da senha normal de login, e respeita empresa, "
    "unidade, papel e permissões do usuário autenticado."
)

st.success(
    "Acesso administrativo confirmado nesta sessão. O desbloqueio expira após "
    "3 minutos sem atividade real e a tela é bloqueada automaticamente em seguida."
)
st.info(
    "Ações críticas permanecem protegidas por nova confirmação do PIN administrativo "
    "no momento da execução, mesmo enquanto a área estiver desbloqueada."
)

render_admin_proprietario(
    identidade=identity,
    session_factory=session_factory,
)
