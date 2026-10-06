from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

import application.ai_router_runtime as runtime
from core.ai_router import CapabilityIA
from core.seguranca.contexto import ContextoExecucao


@dataclass(frozen=True)
class Config:
    configuracao_id: str
    servico: str
    provedor: str
    habilitada: bool
    homologada: bool
    parametros: dict[str, object]


class RepoFake:
    def __init__(self, _session) -> None:
        pass

    def listar(self, *, tenant_id: str, unidade_id: str):
        assert tenant_id == "tenant-a"
        assert unidade_id == "loja-1"
        return (
            Config(
                configuracao_id="ia.generativa--gemini",
                servico="ia.generativa",
                provedor="gemini",
                habilitada=True,
                homologada=True,
                parametros={"model": "gemini-3.6-flash"},
            ),
            Config(
                configuracao_id="ia.generativa--openai",
                servico="ia.generativa",
                provedor="openai",
                habilitada=True,
                homologada=True,
                parametros={"model": "gpt-5.6-luna"},
            ),
        )


@pytest.fixture
def contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id="loja-1",
        usuario_id="admin-a",
        papeis=frozenset(),
        permissoes=frozenset(),
        correlation_id="corr-openai-primary",
        solicitado_em=datetime(2026, 10, 6, 16, 0, tzinfo=timezone.utc),
        origem="tests",
        unidades_permitidas=frozenset({"loja-1"}),
    )


def test_openai_e_rota_textual_primaria_e_gemini_permanece_para_audio(
    monkeypatch,
    contexto: ContextoExecucao,
) -> None:
    monkeypatch.setattr(
        runtime,
        "RepositorioConfiguracoesExternasSQLAlchemy",
        RepoFake,
    )

    rotas = runtime._rotas_homologadas(
        session=object(),  # type: ignore[arg-type]
        contexto=contexto,
    )

    planning = sorted(
        (
            route
            for route in rotas
            if route.capability is CapabilityIA.TOOL_PLANNING
        ),
        key=lambda route: -route.prioridade,
    )
    interpretation = sorted(
        (
            route
            for route in rotas
            if route.capability is CapabilityIA.ATENDIMENTO_INTERPRETACAO
        ),
        key=lambda route: -route.prioridade,
    )
    transcription = [
        route
        for route in rotas
        if route.capability is CapabilityIA.ATENDIMENTO_TRANSCRICAO
    ]

    assert [(route.provider, route.model, route.prioridade) for route in planning] == [
        ("openai", "gpt-5.6-luna", 200),
        ("gemini", "gemini-3.6-flash", 100),
    ]
    assert [route.provider for route in interpretation] == ["openai", "gemini"]
    assert [(route.provider, route.model) for route in transcription] == [
        ("gemini", "gemini-3.6-flash")
    ]


def test_prioridade_explicita_pode_governar_fallback() -> None:
    assert runtime._prioridade(
        provider="openai",
        parametros={"route_priority": "350"},
    ) == 350
    assert runtime._prioridade(
        provider="gemini",
        parametros={"route_priority": 50},
    ) == 50
