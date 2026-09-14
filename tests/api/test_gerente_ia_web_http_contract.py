from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

import http_api.gerente_ia_web as modulo
from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import (
    NaturezaTool,
    PreviewAcao,
    RegistroGerencial,
    ResultadoTool,
    ToolGerenteIA,
    fingerprint_preview,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao


def _contexto(permissoes: frozenset[Permissao]) -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-sessao",
        unidade_id="unidade-sessao",
        usuario_id="usuario-1",
        papeis=frozenset({Papel.GERENTE}),
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


@dataclass(frozen=True)
class IdentidadeAssistenteFake:
    nome_publico: str = "Lina"


class AppFake:
    def __init__(self) -> None:
        self.contextos: list[ContextoExecucao] = []
        self.erro: Exception | None = None

    def _capturar(self, contexto: ContextoExecucao) -> None:
        if self.erro is not None:
            raise self.erro
        self.contextos.append(contexto)

    def perguntar(self, *, contexto: ContextoExecucao, pergunta: str):
        self._capturar(contexto)
        chamada = modulo.ChamadaTool.de_dict("consultar_atrasos", {})
        resultado = ResultadoTool(
            tool=ToolGerenteIA.CONSULTAR_ATRASOS,
            natureza=NaturezaTool.CONSULTA,
            registros=(RegistroGerencial("resumo", (("pergunta", pergunta),)),),
            correlation_id=contexto.correlation_id,
        )
        return IdentidadeAssistenteFake(), chamada, resultado

    def executar_tool(self, *, contexto: ContextoExecucao, chamada):
        self._capturar(contexto)
        agora = datetime.now(timezone.utc)
        impacto = RegistroGerencial("pedido", (("prioridade", "alta"),))
        argumentos = tuple(sorted(chamada.args().items()))
        fingerprint = fingerprint_preview(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            tool=ToolGerenteIA.PRIORIZAR_PEDIDO,
            recurso_id="pedido-1",
            argumentos=argumentos,
            impacto=impacto,
            motivo="atraso",
            criado_por=contexto.usuario_id,
        )
        return PreviewAcao(
            preview_id="preview-1",
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            tool=ToolGerenteIA.PRIORIZAR_PEDIDO,
            recurso_id="pedido-1",
            argumentos=argumentos,
            impacto=impacto,
            motivo="atraso",
            criado_por=contexto.usuario_id,
            criado_em=agora,
            expira_em=agora + timedelta(minutes=10),
            fingerprint=fingerprint,
        )

    def confirmar_acao(self, *, contexto: ContextoExecucao, **kwargs: Any):
        self._capturar(contexto)
        return {"preview_id": kwargs["preview_id"], "resultado": "ok"}


def _client(monkeypatch, permissoes: frozenset[Permissao] | None):
    fake = AppFake()
    monkeypatch.setattr(modulo, "AplicacaoGerenteIAWebV1", lambda *args, **kwargs: fake)
    app = FastAPI()
    identidade = None if permissoes is None else IdentidadeFake(permissoes)
    app.include_router(
        modulo.build_gerente_ia_web_router(
            session_factory=lambda: None,
            auth_runtime=AuthFake(identidade),  # type: ignore[arg-type]
        )
    )
    return TestClient(app), fake


def test_rotas_wp028_expostas(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.GERENTE_IA_CONSULTAR}))
    paths = set(client.app.openapi()["paths"])
    assert "/v1/gerente-ia/perguntar" in paths
    assert "/v1/gerente-ia/tools" in paths
    assert "/v1/gerente-ia/confirmar" in paths


def test_exige_sessao_assinada(monkeypatch) -> None:
    client, _ = _client(monkeypatch, None)
    response = client.post("/v1/gerente-ia/perguntar", json={"pergunta": "status"})
    assert response.status_code == 401


def test_exige_permissao_canonica(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset())
    response = client.post("/v1/gerente-ia/perguntar", json={"pergunta": "status"})
    assert response.status_code == 403


def test_perguntar_preserva_escopo_da_sessao_e_ignora_headers(monkeypatch) -> None:
    client, fake = _client(monkeypatch, frozenset({Permissao.GERENTE_IA_CONSULTAR}))
    response = client.post(
        "/v1/gerente-ia/perguntar",
        json={"pergunta": "pedidos atrasados"},
        headers={"X-Tenant-ID": "tenant-atacante", "X-Unit-ID": "unidade-atacante"},
    )
    assert response.status_code == 200
    assert response.json()["nome_assistente"] == "Lina"
    assert fake.contextos[-1].tenant_id == "tenant-sessao"
    assert fake.contextos[-1].unidade_id == "unidade-sessao"


def test_tool_mutavel_retorna_preview_sem_executar_acao(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.GERENTE_IA_CONSULTAR}))
    response = client.post(
        "/v1/gerente-ia/tools",
        json={"tool": "priorizar_pedido", "argumentos": {"pedido_id": "pedido-1", "motivo": "atraso"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tipo"] == "PreviewAcao"
    assert body["resultado"]["preview_id"] == "preview-1"
    assert body["resultado"]["status"] == "pendente"


def test_confirmacao_exige_permissao_de_execucao(monkeypatch) -> None:
    client, _ = _client(monkeypatch, frozenset({Permissao.GERENTE_IA_CONSULTAR}))
    response = client.post(
        "/v1/gerente-ia/confirmar",
        json={"preview_id": "p", "fingerprint": "f", "idempotency_key": "i"},
    )
    assert response.status_code == 403


def test_confirmacao_com_permissao_delega_contexto_assinado(monkeypatch) -> None:
    client, fake = _client(
        monkeypatch,
        frozenset({Permissao.GERENTE_IA_CONSULTAR, Permissao.GERENTE_IA_EXECUTAR_ACAO}),
    )
    response = client.post(
        "/v1/gerente-ia/confirmar",
        json={"preview_id": "p", "fingerprint": "f", "idempotency_key": "i"},
    )
    assert response.status_code == 200
    assert response.json()["resultado"]["preview_id"] == "p"
    assert fake.contextos[-1].tenant_id == "tenant-sessao"


def test_conflito_de_fingerprint_retorna_409(monkeypatch) -> None:
    client, fake = _client(
        monkeypatch,
        frozenset({Permissao.GERENTE_IA_CONSULTAR, Permissao.GERENTE_IA_EXECUTAR_ACAO}),
    )
    fake.erro = ErroGerenteIA("fingerprint_divergente")
    response = client.post(
        "/v1/gerente-ia/confirmar",
        json={"preview_id": "p", "fingerprint": "f", "idempotency_key": "i"},
    )
    assert response.status_code == 409
