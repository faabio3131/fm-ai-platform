from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import http_api.pagamentos_web as modulo
from application.pagamentos_web import PagamentoWeb, TransacaoPagamentoWeb
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao


def _contexto(permissoes: frozenset[Permissao]) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-sessao",
        unidade_id="unidade-sessao",
        usuario_id="usuario-1",
        papeis=frozenset({Papel.FINANCEIRO}),
        permissoes=permissoes,
        correlation_id="corr-1",
        solicitado_em=datetime.now(timezone.utc),
        origem="teste",
        unidades_permitidas=frozenset({"unidade-sessao"}),
    )


class IdentidadeFake:
    def __init__(self, permissoes: frozenset[Permissao]) -> None:
        self.permissoes = permissoes

    def contexto(self, *, origem: str, correlation_id: str | None) -> ContextoExecucao:
        base = _contexto(self.permissoes)
        return ContextoExecucao(
            tenant_id=base.tenant_id,
            unidade_id=base.unidade_id,
            usuario_id=base.usuario_id,
            papeis=base.papeis,
            permissoes=base.permissoes,
            correlation_id=correlation_id or base.correlation_id,
            solicitado_em=base.solicitado_em,
            origem=origem,
            unidades_permitidas=base.unidades_permitidas,
        )


class AuthFake:
    def __init__(self, identidade: IdentidadeFake | None) -> None:
        self.identidade = identidade

    def resolver_identidade(self, request):
        return self.identidade


@dataclass
class AppFake:
    contexto: ContextoExecucao | None = None
    reconciliacoes: int = 0

    def _snapshot(self) -> PagamentoWeb:
        agora = datetime.now(timezone.utc)
        return PagamentoWeb(
            pagamento_id="pay-1",
            pedido_id="ped-1",
            status="pendente",
            metodo="pix",
            valor_previsto="10.00",
            valor_pago="0.00",
            valor_estornado="0.00",
            saldo="10.00",
            moeda="BRL",
            provedor="pagbank",
            versao=1,
            atualizado_em=agora,
            transacoes=(
                TransacaoPagamentoWeb(
                    transacao_id="tx-1",
                    tipo="iniciacao",
                    status="pendente",
                    valor="0.00",
                    metodo="pix",
                    provedor="pagbank",
                    id_externo="ORDE_1",
                    occurred_at=agora,
                    correlation_id="corr-1",
                    erro_normalizado=None,
                ),
            ),
        )

    def obter(self, *, contexto: ContextoExecucao, pagamento_id: str) -> PagamentoWeb:
        self.contexto = contexto
        if pagamento_id == "ausente":
            raise LookupError("pagamento_nao_encontrado")
        return self._snapshot()

    def reconciliar_pagbank(self, *, contexto: ContextoExecucao, pagamento_id: str) -> PagamentoWeb:
        self.contexto = contexto
        if Permissao.PAGAMENTO_CONFIRMAR not in contexto.permissoes:
            raise PermissionError("seguranca.pagamentos_permissao_exigida")
        self.reconciliacoes += 1
        return self._snapshot()


def _client(monkeypatch, permissoes: frozenset[Permissao] | None):
    fake = AppFake()
    monkeypatch.setattr(modulo, "AplicacaoPagamentosWebV1", lambda *args, **kwargs: fake)
    app = FastAPI()
    identidade = None if permissoes is None else IdentidadeFake(permissoes)
    app.include_router(
        modulo.build_pagamentos_web_router(
            session_factory=lambda: None,
            auth_runtime=AuthFake(identidade),  # type: ignore[arg-type]
        )
    )
    return TestClient(app), fake


def test_rotas_wp029_expostas(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.FINANCEIRO_VISUALIZAR}))
    paths = set(client.app.openapi()["paths"])
    assert "/v1/pagamentos/{pagamento_id}" in paths
    assert "/v1/pagamentos/{pagamento_id}/reconciliar-pagbank" in paths


def test_exige_sessao_e_permissao_financeira(monkeypatch) -> None:
    client, _ = _client(monkeypatch, None)
    assert client.get("/v1/pagamentos/pay-1").status_code == 401
    client, _ = _client(monkeypatch, frozenset())
    assert client.get("/v1/pagamentos/pay-1").status_code == 403


def test_consulta_preserva_escopo_assinado_e_ignora_headers(monkeypatch) -> None:
    client, fake = _client(monkeypatch, frozenset({Permissao.FINANCEIRO_VISUALIZAR}))
    response = client.get(
        "/v1/pagamentos/pay-1",
        headers={"X-Tenant-ID": "atacante", "X-Unit-ID": "outra"},
    )
    assert response.status_code == 200
    assert response.json()["pagamento_id"] == "pay-1"
    assert fake.contexto is not None
    assert fake.contexto.tenant_id == "tenant-sessao"
    assert fake.contexto.unidade_id == "unidade-sessao"


def test_pagamento_inexistente_retorna_404(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.FINANCEIRO_VISUALIZAR}))
    assert client.get("/v1/pagamentos/ausente").status_code == 404


def test_reconciliacao_exige_confirmacao_e_delega_uma_vez(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.FINANCEIRO_VISUALIZAR}))
    assert client.post("/v1/pagamentos/pay-1/reconciliar-pagbank").status_code == 403
    client, fake = _client(
        monkeypatch,
        frozenset({Permissao.FINANCEIRO_VISUALIZAR, Permissao.PAGAMENTO_CONFIRMAR}),
    )
    response = client.post("/v1/pagamentos/pay-1/reconciliar-pagbank")
    assert response.status_code == 200
    assert fake.reconciliacoes == 1


def test_resposta_nao_expoe_segredo(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.FINANCEIRO_VISUALIZAR}))
    texto = client.get("/v1/pagamentos/pay-1").text.lower()
    assert "token" not in texto
    assert "secret" not in texto
