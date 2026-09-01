from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core.integracoes import (
    AmbienteIntegracao,
    ServicoConfiguracoesExternas,
)
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

TENANT = "tenant-http-whatsapp"
UNIDADE = "unidade-http-whatsapp"
AGORA = datetime(2026, 8, 31, 22, 30, tzinfo=timezone.utc)
APP_SECRET = "app-secret-whatsapp-f4f"
VERIFY_TOKEN = "verify-whatsapp-f4f"


class RuntimeCanalCaptura:
    def __init__(self) -> None:
        self.mensagens = []

    def processar_mensagem(self, **kwargs):
        self.mensagens.append(kwargs)
        return None


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id=TENANT,
        unidade_id=UNIDADE,
        usuario_id="admin-whatsapp-f4f",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-whatsapp-http-f4f",
        solicitado_em=AGORA,
        origem="tests.whatsapp-http-f4f",
        unidades_permitidas=frozenset({UNIDADE}),
    )


def _configurar(
    session: Session,
    store: ReferenceSecretStore,
    *,
    homologar: bool,
) -> None:
    contexto = _contexto()
    credenciais = ServicoCredenciaisReferenciadas(session, store)
    for finalidade, referencia in (
        ("mensageria_whatsapp_access_token", "mapping:wa-token"),
        ("mensageria_whatsapp_app_secret", "mapping:wa-secret"),
        ("mensageria_whatsapp_webhook_verify_token", "mapping:wa-verify"),
    ):
        credenciais.rotacionar(
            contexto=contexto,
            provedor="meta",
            finalidade=finalidade,
            nova_referencia=referencia,
        )

    servico = ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )
    servico.configurar(
        contexto=contexto,
        configuracao_id="mensageria.whatsapp--meta",
        servico="mensageria.whatsapp",
        provedor="meta",
        conta_externa="whatsapp-principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "business_account_id": "waba-f4f",
            "phone_number_id": "phone-f4f",
            "app_id": "app-f4f",
        },
        finalidades_credenciais={
            "access_token": "mensageria_whatsapp_access_token",
            "app_secret": "mensageria_whatsapp_app_secret",
            "webhook_verify_token": "mensageria_whatsapp_webhook_verify_token",
        },
        habilitada=True,
        versao_esperada=0,
    )
    if homologar:
        servico.registrar_homologacao(
            contexto=contexto,
            configuracao_id="mensageria.whatsapp--meta",
            evidencia_ref="evidence://meta/whatsapp/f4f-test",
            versao_esperada=1,
        )
    session.commit()


def _client(*, homologar: bool):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    run_migrations(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = RuntimeSettings(
        RuntimeEnvironment.TEST,
        "sqlite://",
        TENANT,
        UNIDADE,
    )
    store = ReferenceSecretStore(
        mapping={
            "wa-token": "access-token-f4f",
            "wa-secret": APP_SECRET,
            "wa-verify": VERIFY_TOKEN,
        }
    )
    with factory() as session:
        _configurar(session, store, homologar=homologar)
    runtime = RuntimeCanalCaptura()
    app = build_http_app(
        settings=settings,
        engine=engine,
        session_factory=factory,
        whatsapp_secret_store_factory=lambda _session: store,
        whatsapp_runtime=runtime,
    )
    return TestClient(app), runtime


def _payload() -> bytes:
    return (
        b'{"object":"whatsapp_business_account","entry":[{"id":"waba-f4f",'
        b'"changes":[{"field":"messages","value":{"messages":[{'
        b'"from":"5511999999999","id":"wamid-http-f4f","timestamp":"1",'
        b'"type":"text","text":{"body":"Oi"}}]}}]}]}'
    )


def _assinatura(payload: bytes) -> str:
    return "sha256=" + hmac.new(
        APP_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()


def test_get_challenge_funciona_antes_da_homologacao_final() -> None:
    client, _runtime = _client(homologar=False)
    resposta = client.get(
        f"/webhooks/meta/whatsapp/{TENANT}/{UNIDADE}",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": VERIFY_TOKEN,
            "hub.challenge": "challenge-f4f",
        },
    )
    assert resposta.status_code == 200
    assert resposta.text == "challenge-f4f"


def test_post_whatsapp_exige_integracao_homologada() -> None:
    client, runtime = _client(homologar=False)
    payload = _payload()
    resposta = client.post(
        f"/webhooks/meta/whatsapp/{TENANT}/{UNIDADE}",
        content=payload,
        headers={"x-hub-signature-256": _assinatura(payload)},
    )
    assert resposta.status_code == 503
    assert runtime.mensagens == []


def test_post_assinado_roteia_mensagem_no_escopo_correto() -> None:
    client, runtime = _client(homologar=True)
    payload = _payload()
    resposta = client.post(
        f"/webhooks/meta/whatsapp/{TENANT}/{UNIDADE}",
        content=payload,
        headers={"x-hub-signature-256": _assinatura(payload)},
    )
    assert resposta.status_code == 204
    assert len(runtime.mensagens) == 1
    chamada = runtime.mensagens[0]
    assert chamada["tenant_id"] == TENANT
    assert chamada["unidade_id"] == UNIDADE
    assert chamada["mensagem"].mensagem_id == "wamid-http-f4f"
    assert chamada["mensagem"].texto == "Oi"


def test_post_assinatura_invalida_falha_fechado() -> None:
    client, runtime = _client(homologar=True)
    resposta = client.post(
        f"/webhooks/meta/whatsapp/{TENANT}/{UNIDADE}",
        content=_payload(),
        headers={"x-hub-signature-256": "sha256=" + "0" * 64},
    )
    assert resposta.status_code == 401
    assert runtime.mensagens == []


def test_post_nao_roteia_para_unidade_sem_configuracao() -> None:
    client, runtime = _client(homologar=True)
    payload = _payload()
    resposta = client.post(
        f"/webhooks/meta/whatsapp/{TENANT}/unidade-outra",
        content=payload,
        headers={"x-hub-signature-256": _assinatura(payload)},
    )
    assert resposta.status_code == 503
    assert runtime.mensagens == []
