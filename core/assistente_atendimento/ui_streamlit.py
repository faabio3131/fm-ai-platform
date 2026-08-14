"""Entrada canônica do Assistente de Atendimento no Streamlit.

O módulo histórico ``core.mica`` permanece apenas como compatibilidade do fluxo
isolado de teste, até a remoção contratual de seus nomes Python antigos.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from .flags import assistente_atendimento_v1_enabled


def render_assistente_atendimento_v1(
    *,
    session_factory: Callable[[], Any],
    produto_cls: Any,
    generate_content: Callable[..., Any],
    nome_publico: str,
) -> None:
    nome = " ".join(nome_publico.split()) or "Assistente de Atendimento"
    if not assistente_atendimento_v1_enabled():
        st.header(f"💬 {nome} — Atendimento seguro V1")
        st.info(
            "O Assistente de Atendimento está desativado neste ambiente. "
            "O fluxo legado de venda automática foi removido por segurança."
        )
        return

    # Import tardio e exclusivo do harness E2E mantém componentes históricos
    # fora do caminho de produção.
    from core.mica.ui_streamlit import render_mica_v1

    render_mica_v1(
        session_factory=session_factory,
        produto_cls=produto_cls,
        generate_content=generate_content,
        nome_publico=nome,
    )
