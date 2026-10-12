"""Simulador desligado por padrão e sem acesso público."""
from __future__ import annotations

from tests.api.test_estoque_http_contract import _infra, _login, _step_up


def test_simulador_desabilitado_por_padrao(monkeypatch):
    monkeypatch.delenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", raising=False)
    _, client = _infra(monkeypatch)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "Olá!"},
    )
    assert response.status_code == 404
    assert response.json() == {"erro": "simulador.desabilitado"}


def test_simulador_exige_autenticacao_quando_ativado(monkeypatch):
    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    _, client = _infra(monkeypatch)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "Olá!"},
    )
    assert response.status_code in (401, 403)
    assert response.status_code != 200


def test_simulador_exige_step_up_administrativo(monkeypatch):
    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    _, client = _infra(monkeypatch)
    _login(client)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "Olá!"},
    )
    assert response.status_code == 403
    assert response.json()["erro"] == "seguranca.admin_step_up_exigido"


def test_simulador_conecta_router_real_sem_enviar_whatsapp(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    calls = []
    class RouterDeTeste:
        def executar(self, solicitacao):
            calls.append(solicitacao)
            return SimpleNamespace(
                conteudo="Posso apresentar categorias, sem inventar preços.",
                provider="gemini",
                model="gemini-modelo-de-teste",
                fallback_used=False,
            )
    monkeypatch.setattr(
        "http_api.assistente_simulador_homologacao.construir_ai_model_router",
        lambda **_: RouterDeTeste(),
    )
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "Quais opções há?"},
    )
    assert response.status_code == 200
    assert response.json()["provedor"] == "gemini"
    assert response.json()["fallback"] is False
    assert len(calls) == 1
