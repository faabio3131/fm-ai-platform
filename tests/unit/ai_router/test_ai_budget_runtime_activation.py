"""Ativação financeira é explícita, segura e não depende de credencial real."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from application.ai_router_runtime import construir_ai_model_router
from core.seguranca.contexto import ContextoExecucao
from infra.ai_budget_sqlalchemy import OrcamentoIndisponivelIA


def test_ativacao_financeira_exige_catalogo_precos_sem_chamar_provedor(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FM_AI_FRANCHISE_ENFORCEMENT_ENABLED", "1")
    engine = create_engine("sqlite+pysqlite:///:memory:")
    contexto = ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="proprietario",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="budget-activation-test",
        solicitado_em=datetime(2026, 10, 18, tzinfo=timezone.utc),
        origem="test",
        unidades_permitidas=frozenset({"loja-1"}),
    )
    with Session(engine) as session:
        with pytest.raises(OrcamentoIndisponivelIA, match="ai_catalogo_precos_obrigatorio"):
            construir_ai_model_router(session=session, contexto=contexto)
    engine.dispose()
