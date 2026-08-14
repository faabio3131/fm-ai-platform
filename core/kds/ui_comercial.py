"""Composição da tela comercial do KDS V1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao

from .ui_roteamento import render_roteamento_kds
from .ui_runtime import render_kds as render_fila_kds


def render_kds(
    *,
    engine: Any,
    session_factory: Callable[[], Session],
    permitir_simulacao_offline: bool = False,
    contexto: ContextoExecucao | None = None,
) -> None:
    render_roteamento_kds(session_factory=session_factory, contexto=contexto)
    render_fila_kds(
        engine=engine,
        session_factory=session_factory,
        permitir_simulacao_offline=permitir_simulacao_offline,
        contexto=contexto,
    )
