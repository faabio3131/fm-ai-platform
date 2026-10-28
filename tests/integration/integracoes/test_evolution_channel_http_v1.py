from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from core.integracoes import AmbienteIntegracao, ServicoConfiguracoesExternas
from core.integracoes.evolution import nome_instancia_evolution
from core.runtime.config import RuntimeEnvironment, RuntimeSettings
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from http_api.app import build_http_app
from infra.integracoes import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from migrations.runner import run_migrations

TENANT = "tenant-evolution-http"
UNIT = "unit-evolution-http"
TOKEN = "webhook-token-evolution-1234567890"


class RuntimeCapture:
    def __init__(self) -> None:
        self.calls = []

    def processar_mensagem(self, **kwargs):
        self.calls.append(kwargs)


def _context() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIT,
        usuario_id="admin-evolution",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-evolution-http",
        solicitado_em=datetime(2026, 10, 28, tzinfo=UTC),
        origem="tests.evolution-http",
        unidades_permitidas=frozenset({UNIT}),
    )


def _client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    store = ReferenceSecretStore(mapping={"evo-key": "platform-key", "evo-hook": TOKEN})
    with factory() as session:
        credentials = ServicoCredenciaisReferenciadas(session, store)
        credentials.rotacionar(
            contexto=_context(),
            provedor="evolution",
            finalidade="mensageria_whatsapp_api_key",
            nova_referencia="mapping:evo-key",
        )
        credentials.rotacionar(
            contexto=_context(),
            provedor="evolution",
            finalidade="mensageria_whatsapp_webhook_token",
            nova_referencia="mapping:evo-hook",
        )
        service = ServicoConfiguracoesExternas(
            repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
            prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
            auditoria=RepositorioAuditoriaEmMemoria(),
        )
        service.configurar(
            contexto=_context(),
            configuracao_id="mensageria.whatsapp--evolution",
            servico="mensageria.whatsapp",
            provedor="evolution",
            conta_externa="evolution-central",
            ambiente=AmbienteIntegracao.HOMOLOGACAO,
            parametros_publicos={
                "base_url": "https://evolution.internal.example",
                "webhook_url": f"https://kordena.example/webhooks/evolution/whatsapp/{TENANT}/{UNIT}",
            },
            finalidades_credenciais={
                "api_key": "mensageria_whatsapp_api_key",
                "webhook_token": "mensageria_whatsapp_webhook_token",
            },
            habilitada=True,
            versao_esperada=0,
        )
        service.registrar_homologacao(
            contexto=_context(),
            configuracao_id="mensageria.whatsapp--evolution",
            evidencia_ref="evidence://evolution/connected",
            versao_esperada=1,
        )
        session.commit()
    runtime = RuntimeCapture()
    app = build_http_app(
        settings=RuntimeSettings(RuntimeEnvironment.TEST, "sqlite://", TENANT, UNIT),
        engine=engine,
        session_factory=factory,
        whatsapp_secret_store_factory=lambda _session: store,
        whatsapp_runtime=runtime,
    )
    return TestClient(app), runtime


def _payload() -> bytes:
    return json.dumps(
        {
            "instance": nome_instancia_evolution(TENANT, UNIT),
            "event": "messages.upsert",
            "data": {
                "key": {
                    "id": "evo-http-1",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "fromMe": False,
                },
                "message": {"conversation": "Quero fazer um pedido"},
                "messageTimestamp": 1,
            },
        }
    ).encode()


def test_webhook_evolution_autenticado_roteia_no_escopo_correto() -> None:
    client, runtime = _client()
    response = client.post(
        f"/webhooks/evolution/whatsapp/{TENANT}/{UNIT}",
        content=_payload(),
        headers={"x-kordena-evolution-auth": TOKEN},
    )
    assert response.status_code == 204
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["tenant_id"] == TENANT
    assert runtime.calls[0]["unidade_id"] == UNIT
    assert runtime.calls[0]["mensagem"].mensagem_id == "evo:evo-http-1"


def test_webhook_evolution_sem_token_falha_fechado() -> None:
    client, runtime = _client()
    response = client.post(
        f"/webhooks/evolution/whatsapp/{TENANT}/{UNIT}", content=_payload()
    )
    assert response.status_code == 401
    assert runtime.calls == []
