"""Contratos reais da API consumida pela Central de Operações.

TestClient executa a aplicação FastAPI, autenticação, serviços e SQLite real
em ambiente TEST. Não intercepta nem simula a resposta de /v1/pedidos.
"""
from tests.api.test_central_pedidos_http_contract import (
    _criar_pedido_pdv,
    _infra,
    _login,
)


def test_board_consulta_api_real_com_cookie_e_paginacao(monkeypatch):
    with _infra(monkeypatch) as client:
        _login(client)
        checkout = _criar_pedido_pdv(client)
        esperado = checkout["comanda"]["pedido_id"]

        response = client.get("/v1/pedidos?pagina=1&tamanho_pagina=100")
        assert response.status_code == 200
        body = response.json()
        assert body["pagina"] == 1
        assert body["tamanho_pagina"] == 100
        assert body["total"] == 1
        assert len(body["itens"]) == 1
        resumo = body["itens"][0]
        assert resumo["pedido_id"] == esperado
        assert isinstance(resumo["status"], str)
        assert isinstance(resumo["quantidade_itens"], int)
        assert isinstance(resumo["canal"], str)
        assert isinstance(resumo["possui_alerta"], bool)


def test_board_api_real_nega_consulta_sem_sessao(monkeypatch):
    with _infra(monkeypatch) as client:
        response = client.get("/v1/pedidos?pagina=1&tamanho_pagina=100")
        assert response.status_code in (401, 403)
        assert "itens" not in response.json()


def test_board_api_real_ignora_escopo_injetado_em_headers(monkeypatch):
    with _infra(monkeypatch) as client:
        _login(client)
        checkout = _criar_pedido_pdv(client)
        esperado = checkout["comanda"]["pedido_id"]

        response = client.get(
            "/v1/pedidos?pagina=1&tamanho_pagina=100",
            headers={"X-Tenant-ID": "outro-tenant", "X-Unit-ID": "outra-unidade"},
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["itens"][0]["pedido_id"] == esperado
