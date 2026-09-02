"""Página comercial mobile/tablet da operação do Garçom V1."""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from core.garcom.flags import garcom_v1_enabled
from core.garcom.ui_streamlit import render_garcom
from core.runtime import build_engine, load_runtime_settings
from core.seguranca.permissoes import Permissao
from infra.seguranca.session_guard import build_session_factory
from infra.streamlit_app.auth_ui import render_identity_sidebar, require_authentication
from migrations.runner import assert_schema_current

load_dotenv()
st.set_page_config(
    page_title="Atendimento do Garçom — Kordena",
    page_icon="📱",
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

if not garcom_v1_enabled():
    st.error(
        "Interface do Garçom indisponível: flag/adapters comerciais ainda não "
        "estão habilitados para este runtime."
    )
    st.stop()

permissoes = identity.permissoes
if (
    Permissao.PEDIDO_VISUALIZAR not in permissoes
    or not ({Permissao.MESA_ABRIR, Permissao.COMANDA_ALTERAR} & permissoes)
):
    st.error("Acesso negado: seu usuário não possui alçada operacional de salão.")
    st.stop()

render_garcom(engine=engine, session_factory=session_factory)
