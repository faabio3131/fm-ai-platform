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


def test_simulador_consulta_maps_para_cep_e_numero_sem_confirmar_numero(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    requisicoes_maps = []
    prompts = []

    class RouterFake:
        def executar(self, solicitacao):
            prompts.append(solicitacao.conteudo)
            return SimpleNamespace(conteudo="Confirme o logradouro e o número.", provider="openai", model="teste", fallback_used=False)

    class MapsFake:
        def geocodificar(self, endereco):
            requisicoes_maps.append(endereco)
            return SimpleNamespace(
                cep="07794-080",
                logradouro="Rua de Teste",
                bairro="Bairro Exemplo",
                endereco_formatado="Rua de Teste, Bairro Exemplo, Brasil",
            )

    monkeypatch.setattr("http_api.assistente_simulador_homologacao.construir_ai_model_router", lambda **_: RouterFake())
    monkeypatch.setattr("http_api.assistente_simulador_homologacao.FabricaAdaptersExternos",
                        lambda **_: SimpleNamespace(google_maps=lambda **__: MapsFake()))
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "Quero entrega no CEP 07794080 número 53."},
    )
    assert response.status_code == 200
    assert response.json()["maps_status"] == "endereco_aproximado"
    assert requisicoes_maps == ["07794-080, Brasil"]
    assert "Rua de Teste" in prompts[0]
    assert "o número NÃO foi validado" in prompts[0]


def test_simulador_reutiliza_cep_do_historico_sem_inventar_endereco(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    consultas = []
    prompts = []

    class RouterFake:
        def executar(self, solicitacao):
            prompts.append(solicitacao.conteudo)
            return SimpleNamespace(conteudo="Não consegui confirmar o endereço.", provider="openai", model="teste", fallback_used=False)

    class MapsFake:
        def geocodificar(self, endereco):
            consultas.append(endereco)
            return SimpleNamespace(cep=None, logradouro=None, endereco_formatado=None)

    monkeypatch.setattr("http_api.assistente_simulador_homologacao.construir_ai_model_router", lambda **_: RouterFake())
    monkeypatch.setattr("http_api.assistente_simulador_homologacao.FabricaAdaptersExternos",
                        lambda **_: SimpleNamespace(google_maps=lambda **__: MapsFake()))
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)
    response = client.post(
        "/v1/admin/assistente-atendimento/simulador",
        json={"mensagem": "O número é 53.", "historico": ["Quero entrega no CEP 07794080."]},
    )
    assert response.status_code == 200
    assert response.json()["maps_status"] == "resultado_incompleto"
    assert consultas == ["07794-080, Brasil"]
    assert "O número é 53." in prompts[0]
    assert "Nenhum endereço foi verificado" in prompts[0]


def test_simulador_preserva_localidade_parcial_sem_inventar_logradouro(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    prompts = []

    class RouterFake:
        def executar(self, solicitacao):
            prompts.append(solicitacao.conteudo)
            return SimpleNamespace(conteudo="Por favor confirme sua rua.", provider="gemini", model="teste", fallback_used=False)

    class MapsFake:
        def geocodificar(self, endereco):
            assert endereco == "07794-080, Brasil"
            return SimpleNamespace(cep=None, logradouro=None, bairro=None, endereco_formatado="Caieiras, SP, Brasil")

    monkeypatch.setattr("http_api.assistente_simulador_homologacao.construir_ai_model_router", lambda **_: RouterFake())
    monkeypatch.setattr("http_api.assistente_simulador_homologacao.FabricaAdaptersExternos", lambda **_: SimpleNamespace(google_maps=lambda **__: MapsFake()))
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)
    response = client.post("/v1/admin/assistente-atendimento/simulador", json={"mensagem": "Entrega no CEP 07794-080, número 53."})
    assert response.status_code == 200
    assert response.json()["maps_status"] == "localidade_sem_rua"
    assert "Nenhum logradouro foi identificado" in prompts[0]


def test_simulador_rejeita_cep_divergente_do_google(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("FM_AI_ASSISTENTE_SIMULADOR_ENABLED", "true")
    prompts = []

    class RouterFake:
        def executar(self, solicitacao):
            prompts.append(solicitacao.conteudo)
            return SimpleNamespace(conteudo="Não consegui confirmar.", provider="gemini", model="teste", fallback_used=False)

    class MapsFake:
        def geocodificar(self, endereco):
            return SimpleNamespace(cep="99999-999", logradouro="Rua Errada", bairro=None, endereco_formatado="Rua Errada")

    monkeypatch.setattr("http_api.assistente_simulador_homologacao.construir_ai_model_router", lambda **_: RouterFake())
    monkeypatch.setattr("http_api.assistente_simulador_homologacao.FabricaAdaptersExternos", lambda **_: SimpleNamespace(google_maps=lambda **__: MapsFake()))
    _, client = _infra(monkeypatch)
    _login(client)
    _step_up(client)
    response = client.post("/v1/admin/assistente-atendimento/simulador", json={"mensagem": "Entrega no CEP 07794-080 número 53."})
    assert response.status_code == 200
    assert response.json()["maps_status"] == "cep_divergente"
    assert "Rua Errada" not in prompts[0]
