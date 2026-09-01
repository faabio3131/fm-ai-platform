from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    ErroConfiguracaoServico,
    ServicoConfiguracoesExternas,
)
from core.integracoes.provedores import RespostaBinariaProvedor, RespostaProvedor
from core.seguranca.auditoria import RepositorioAuditoriaEmMemoria
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.integracoes import (
    FabricaAdaptersExternos,
    IntegrationConfigBase,
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)
from infra.seguranca.credenciais import ServicoCredenciaisReferenciadas
from infra.seguranca.modelos_orm import SecurityBase


def _contexto(*, unidade: str = "loja-1") -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-a",
        unidade_id=unidade,
        usuario_id=f"admin-{unidade}",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id=f"corr-{unidade}",
        solicitado_em=datetime.now(timezone.utc),
        origem="tests.whatsapp-control-plane",
        unidades_permitidas=frozenset({unidade}),
    )


def _servico(session: Session, store: ReferenceSecretStore) -> ServicoConfiguracoesExternas:
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )


def _configurar_whatsapp(
    *,
    session: Session,
    store: ReferenceSecretStore,
    contexto: ContextoExecucao,
    homologar: bool,
) -> None:
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

    servico = _servico(session, store)
    servico.configurar(
        contexto=contexto,
        configuracao_id="mensageria.whatsapp--meta",
        servico="mensageria.whatsapp",
        provedor="meta",
        conta_externa="whatsapp-principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "business_account_id": "waba-1",
            "phone_number_id": "phone-1",
            "app_id": "app-1",
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
            evidencia_ref="evidence://meta/whatsapp/runtime",
            versao_esperada=1,
        )


class HTTPMidiaWhatsAppCaptura:
    def __init__(self, *, conteudo: bytes = b"ogg-audio") -> None:
        self.conteudo = conteudo
        self.chamadas: list[dict] = []

    def get(self, **kwargs):
        self.chamadas.append(kwargs)
        return RespostaBinariaProvedor(
            status_code=200,
            content=self.conteudo,
            content_type="audio/ogg",
        )


class HTTPWhatsAppCaptura:
    def __init__(self) -> None:
        self.chamadas: list[dict] = []

    def request(self, **kwargs):
        self.chamadas.append(kwargs)
        return RespostaProvedor(
            status_code=200,
            payload={"messages": [{"id": "wamid-runtime-1"}]},
        )


def test_whatsapp_control_plane_envia_e_valida_webhook_com_credenciais_do_escopo() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "wa-token": "token-loja-1",
            "wa-secret": "app-secret-loja-1",
            "wa-verify": "verify-loja-1",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        _configurar_whatsapp(
            session=session,
            store=store,
            contexto=contexto,
            homologar=True,
        )
        http = HTTPWhatsAppCaptura()
        adapter = FabricaAdaptersExternos(
            session=session,
            secret_store=store,
        ).meta(
            contexto=contexto,
            configuracao_id="mensageria.whatsapp--meta",
            http=http,
        )

        mensagem_id = adapter.enviar_whatsapp(
            destinatario="+55 (11) 99999-9999",
            texto="Alerta operacional",
            idempotency_key="alerta-estoque-1",
        )
        assert mensagem_id == "wamid-runtime-1"
        chamada = http.chamadas[0]
        assert chamada["headers"]["Authorization"] == "Bearer token-loja-1"
        assert chamada["url"].endswith("/phone-1/messages")
        assert chamada["json_body"]["to"] == "5511999999999"
        assert chamada["json_body"]["biz_opaque_callback_data"] == "alerta-estoque-1"

        payload = (
            b'{"object":"whatsapp_business_account","entry":[{"id":"waba-1",'
            b'"changes":[{"field":"messages","value":{"statuses":[{"id":'
            b'"wamid-runtime-1"}]}}]}]}'
        )
        assinatura = "sha256=" + hmac.new(
            b"app-secret-loja-1", payload, hashlib.sha256
        ).hexdigest()
        eventos = adapter.normalizar_webhook(
            payload_bruto=payload,
            assinatura=assinatura,
        )
        assert len(eventos) == 1
        assert eventos[0].recurso_id == "wamid-runtime-1"
        assert eventos[0].assinatura_validada is True
        assert adapter.validar_desafio(
            verify_token="verify-loja-1",
            challenge="challenge-123",
        ) == "challenge-123"


def test_whatsapp_control_plane_extrai_texto_e_audio_e_baixa_midia_autenticada() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "wa-token": "token-loja-1",
            "wa-secret": "app-secret-loja-1",
            "wa-verify": "verify-loja-1",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        _configurar_whatsapp(
            session=session,
            store=store,
            contexto=contexto,
            homologar=True,
        )
        http = HTTPWhatsAppCaptura()
        midia = HTTPMidiaWhatsAppCaptura()
        adapter = FabricaAdaptersExternos(
            session=session,
            secret_store=store,
        ).meta(
            contexto=contexto,
            configuracao_id="mensageria.whatsapp--meta",
            http=http,
            media_http=midia,
        )

        payload = (
            b'{"object":"whatsapp_business_account","entry":[{"id":"waba-1",'
            b'"changes":[{"field":"messages","value":{"messages":['
            b'{"from":"5511999999999","id":"wamid-text-1","timestamp":"1",'
            b'"type":"text","text":{"body":"Quero um produto"}},'
            b'{"from":"5511999999999","id":"wamid-audio-1","timestamp":"2",'
            b'"type":"audio","audio":{"id":"media-1","mime_type":"audio/ogg"}}'
            b']}}]}]}'
        )
        assinatura = "sha256=" + hmac.new(
            b"app-secret-loja-1", payload, hashlib.sha256
        ).hexdigest()

        mensagens = adapter.extrair_mensagens_whatsapp(
            payload_bruto=payload,
            assinatura=assinatura,
        )
        assert [mensagem.mensagem_id for mensagem in mensagens] == [
            "wamid-text-1",
            "wamid-audio-1",
        ]
        assert mensagens[0].texto == "Quero um produto"
        assert mensagens[1].media_id == "media-1"

        http.chamadas.clear()
        http.chamadas.append({})
        original_request = http.request

        def request_metadata(**kwargs):
            if kwargs["method"] == "GET":
                return RespostaProvedor(
                    status_code=200,
                    payload={
                        "url": "https://lookaside.example/media-1",
                        "mime_type": "audio/ogg",
                        "file_size": 9,
                    },
                )
            return original_request(**kwargs)

        http.request = request_metadata
        audio, mime_type = adapter.baixar_audio_whatsapp(
            media_id="media-1",
            mime_type_declarado="audio/ogg",
        )
        assert audio == b"ogg-audio"
        assert mime_type == "audio/ogg"
        assert midia.chamadas[0]["headers"]["Authorization"] == "Bearer token-loja-1"


def test_whatsapp_control_plane_falha_fechado_sem_homologacao() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "wa-token": "token-loja-1",
            "wa-secret": "app-secret-loja-1",
            "wa-verify": "verify-loja-1",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        _configurar_whatsapp(
            session=session,
            store=store,
            contexto=contexto,
            homologar=False,
        )
        with pytest.raises(ErroConfiguracaoServico, match="integracao_nao_homologada"):
            FabricaAdaptersExternos(
                session=session,
                secret_store=store,
            ).meta(
                contexto=contexto,
                configuracao_id="mensageria.whatsapp--meta",
                http=HTTPWhatsAppCaptura(),
            )
