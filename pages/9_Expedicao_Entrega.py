"""Página comercial autenticada de Expedição e Entrega V1."""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from core.entrega.flags import entrega_v1_enabled
from core.entrega.ui_streamlit import render_entrega
from core.runtime import build_engine, load_runtime_settings
from core.seguranca import Papel, Permissao
from infra.seguranca.session_guard import build_session_factory
from infra.streamlit_app.auth_ui import render_identity_sidebar, require_authentication
from migrations.runner import assert_schema_current

load_dotenv()
st.set_page_config(
    page_title="Expedição e Entrega — Kordena",
    page_icon="🛵",
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

if not entrega_v1_enabled():
    st.error(
        "Expedição e Entrega indisponíveis: flag/adapters comerciais ainda não "
        "estão habilitados para este runtime."
    )
    st.stop()

papeis_operacionais = {
    Papel.EXPEDICAO,
    Papel.ENTREGADOR,
    Papel.GERENTE,
    Papel.ADMINISTRADOR,
}
if (
    Permissao.EXPEDICAO_OPERAR not in identity.permissoes
    or not (identity.papeis & papeis_operacionais)
):
    st.error("Acesso negado: seu usuário não possui alçada de Expedição/Entrega.")
    st.stop()

render_entrega(session_factory=session_factory)
