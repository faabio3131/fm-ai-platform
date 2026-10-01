from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import http_api.campanhas_web as modulo
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao


class IdentidadeFake:
    def __init__(self, permissoes: frozenset[Permissao]) -> None:
        self.permissoes = permissoes
        self.tenant_id = "tenant-sessao"
        self.unidade_id = "unidade-sessao"
        self.usuario_id = "usuario-1"

    def contexto(self, *, origem: str, correlation_id: str | None):
        return ContextoExecucao(
            tenant_id=self.tenant_id,
            unidade_id=self.unidade_id,
            usuario_id=self.usuario_id,
            papeis=frozenset({Papel.ADMINISTRADOR}),
            permissoes=self.permissoes,
            correlation_id=correlation_id or "corr-test",
            solicitado_em=datetime.now(timezone.utc),
            origem=origem,
            unidades_permitidas=frozenset({self.unidade_id}),
        )


class AuthFake:
    def __init__(self, identidade: IdentidadeFake | None, *, elevado: bool = True) -> None:
        self.identidade = identidade
        self.elevado = elevado

    def resolver_identidade(self, request):
        return self.identidade

    def admin_status(self, request):
        return self.identidade, self.elevado, None


def _client(monkeypatch, *, elevado: bool = True):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    factory = sessionmaker(bind=engine)
    permissoes = frozenset(
        {
            Permissao.ADMIN_ACESSAR,
            Permissao.CLIENTE_VISUALIZAR,
            Permissao.CAMPANHA_CRIAR,
            Permissao.CAMPANHA_APROVAR,
            Permissao.GERENTE_IA_APROVAR_CAMPANHA,
            Permissao.GERENTE_IA_PREPARAR_ACAO,
        }
    )
    auth = AuthFake(IdentidadeFake(permissoes), elevado=elevado)
    app = FastAPI()
    app.include_router(
        modulo.build_campanhas_web_router(
            session_factory=factory,
            auth_runtime=auth,  # type: ignore[arg-type]
        )
    )
    return TestClient(app)


def test_rotas_completas_wp017_expostas() -> None:
    app = FastAPI()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    factory = sessionmaker(bind=engine)
    auth = AuthFake(IdentidadeFake(frozenset(Permissao)))
    app.include_router(
        modulo.build_campanhas_web_router(
            session_factory=factory,
            auth_runtime=auth,  # type: ignore[arg-type]
        )
    )
    paths = set(app.openapi()["paths"])
    assert "/v1/campanhas" in paths
    assert "/v1/campanhas/{campanha_id}" in paths
    assert "/v1/campanhas/{campanha_id}/audiencia" in paths
    assert "/v1/campanhas/{campanha_id}/submeter" in paths
    assert "/v1/campanhas/{campanha_id}/aprovar" in paths
    assert "/v1/campanhas/{campanha_id}/publicar" in paths
    assert "/v1/campanhas/{campanha_id}/despachar" in paths
    assert "/v1/campanhas/{campanha_id}/historico" in paths


def test_listagem_usa_tenant_e_unidade_da_sessao_e_ignora_headers(monkeypatch) -> None:
    capturados: list[ContextoExecucao] = []

    def listar(*, session_factory, contexto):
        capturados.append(contexto)
        return ()

    monkeypatch.setattr(modulo, "listar_campanhas_web", listar)
    client = _client(monkeypatch)
    response = client.get(
        "/v1/campanhas",
        headers={"X-Tenant-ID": "tenant-atacante", "X-Unit-ID": "unidade-atacante"},
    )
    assert response.status_code == 200
    assert capturados[-1].tenant_id == "tenant-sessao"
    assert capturados[-1].unidade_id == "unidade-sessao"


def test_criacao_exige_idempotency_key(monkeypatch) -> None:
    monkeypatch.setattr(modulo, "criar_campanha_web", lambda **kwargs: {})
    client = _client(monkeypatch)
    response = client.post(
        "/v1/campanhas",
        json={
            "canal": "whatsapp",
            "finalidade": "promocoes",
            "objetivo": "reativacao",
            "texto_base": "volte",
        },
    )
    assert response.status_code == 400
    assert response.json()["erro"] == "idempotency_key_obrigatoria"


def test_aprovacao_web_exige_step_up(monkeypatch) -> None:
    monkeypatch.setattr(modulo, "aprovar_campanha_web", lambda **kwargs: {})
    client = _client(monkeypatch, elevado=False)
    response = client.post(
        "/v1/campanhas/camp-1/aprovar",
        headers={"Idempotency-Key": "approve-1"},
        json={"fingerprint": "a" * 64},
    )
    assert response.status_code == 403
    assert response.json()["erro"] == "seguranca.admin_step_up_exigido"


def test_aprovacao_delega_fingerprint_e_contexto_humano(monkeypatch) -> None:
    capturado: dict[str, object] = {}

    def aprovar(**kwargs):
        capturado.update(kwargs)
        return {
            "campanha_id": kwargs["campanha_id"],
            "fingerprint": kwargs["fingerprint"],
        }

    monkeypatch.setattr(modulo, "aprovar_campanha_web", aprovar)
    client = _client(monkeypatch, elevado=True)
    response = client.post(
        "/v1/campanhas/camp-1/aprovar",
        headers={"Idempotency-Key": "approve-1"},
        json={"fingerprint": "a" * 64},
    )
    assert response.status_code == 200
    assert capturado["fingerprint"] == "a" * 64
    contexto = capturado["contexto"]
    assert isinstance(contexto, ContextoExecucao)
    assert contexto.tenant_id == "tenant-sessao"
    assert contexto.identidade_sistema is False
