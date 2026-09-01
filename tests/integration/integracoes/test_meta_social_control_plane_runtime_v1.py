from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.integracoes import (
    AmbienteIntegracao,
    ErroConfiguracaoServico,
    ServicoConfiguracoesExternas,
)
from core.integracoes.provedores import RespostaProvedor
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
        origem="tests.meta-social-control-plane",
        unidades_permitidas=frozenset({unidade}),
    )


def _servico(session: Session, store: ReferenceSecretStore) -> ServicoConfiguracoesExternas:
    return ServicoConfiguracoesExternas(
        repositorio=RepositorioConfiguracoesExternasSQLAlchemy(session),
        prontidao_credenciais=ProntidaoCredenciaisSQLAlchemy(session, store),
        auditoria=RepositorioAuditoriaEmMemoria(),
    )


def _rotacionar_meta(
    *,
    session: Session,
    store: ReferenceSecretStore,
    contexto: ContextoExecucao,
    prefixo: str,
) -> None:
    credenciais = ServicoCredenciaisReferenciadas(session, store)
    credenciais.rotacionar(
        contexto=contexto,
        provedor="meta",
        finalidade="social_facebook_access_token",
        nova_referencia=f"mapping:{prefixo}-fb-token",
    )
    credenciais.rotacionar(
        contexto=contexto,
        provedor="meta",
        finalidade="social_facebook_app_secret",
        nova_referencia=f"mapping:{prefixo}-fb-secret",
    )
    credenciais.rotacionar(
        contexto=contexto,
        provedor="meta",
        finalidade="social_instagram_access_token",
        nova_referencia=f"mapping:{prefixo}-ig-token",
    )
    credenciais.rotacionar(
        contexto=contexto,
        provedor="meta",
        finalidade="social_instagram_app_secret",
        nova_referencia=f"mapping:{prefixo}-ig-secret",
    )


def _configurar_e_homologar(
    *,
    servico: ServicoConfiguracoesExternas,
    contexto: ContextoExecucao,
) -> None:
    servico.configurar(
        contexto=contexto,
        configuracao_id="social.facebook--meta",
        servico="social.facebook",
        provedor="meta",
        conta_externa="facebook-principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={"page_id": "page-1", "app_id": "app-1"},
        finalidades_credenciais={
            "access_token": "social_facebook_access_token",
            "app_secret": "social_facebook_app_secret",
        },
        habilitada=True,
        versao_esperada=0,
    )
    servico.registrar_homologacao(
        contexto=contexto,
        configuracao_id="social.facebook--meta",
        evidencia_ref="evidence://meta/facebook/runtime",
        versao_esperada=1,
    )

    servico.configurar(
        contexto=contexto,
        configuracao_id="social.instagram--meta",
        servico="social.instagram",
        provedor="meta",
        conta_externa="instagram-principal",
        ambiente=AmbienteIntegracao.HOMOLOGACAO,
        parametros_publicos={
            "business_account_id": "ig-1",
            "facebook_page_id": "page-1",
            "app_id": "app-1",
        },
        finalidades_credenciais={
            "access_token": "social_instagram_access_token",
            "app_secret": "social_instagram_app_secret",
        },
        habilitada=True,
        versao_esperada=0,
    )
    servico.registrar_homologacao(
        contexto=contexto,
        configuracao_id="social.instagram--meta",
        evidencia_ref="evidence://meta/instagram/runtime",
        versao_esperada=1,
    )


class HTTPMetaCaptura:
    def __init__(self, respostas: list[RespostaProvedor]) -> None:
        self.respostas = respostas
        self.chamadas: list[dict] = []

    def request(self, **kwargs):
        self.chamadas.append(kwargs)
        return self.respostas.pop(0)


def test_meta_social_control_plane_publica_facebook_e_instagram_com_credenciais_do_escopo() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "l1-fb-token": "fb-token-loja-1",
            "l1-fb-secret": "fb-secret-loja-1",
            "l1-ig-token": "ig-token-loja-1",
            "l1-ig-secret": "ig-secret-loja-1",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        _rotacionar_meta(
            session=session,
            store=store,
            contexto=contexto,
            prefixo="l1",
        )
        servico = _servico(session, store)
        _configurar_e_homologar(servico=servico, contexto=contexto)

        fabrica = FabricaAdaptersExternos(session=session, secret_store=store)
        http_fb = HTTPMetaCaptura(
            [RespostaProvedor(status_code=200, payload={"id": "post-123"})]
        )
        post_id = fabrica.meta(
            contexto=contexto,
            configuracao_id="social.facebook--meta",
            http=http_fb,
        ).publicar_facebook(
            mensagem="Oferta do dia",
            idempotency_key="fb-post-1",
        )

        http_ig = HTTPMetaCaptura(
            [
                RespostaProvedor(status_code=200, payload={"id": "container-123"}),
                RespostaProvedor(status_code=200, payload={"id": "media-123"}),
            ]
        )
        media_id = fabrica.meta(
            contexto=contexto,
            configuracao_id="social.instagram--meta",
            http=http_ig,
        ).publicar_instagram(
            image_url="https://example.test/oferta.jpg",
            legenda="Oferta do dia",
            idempotency_key="ig-post-1",
        )

        assert post_id == "post-123"
        assert media_id == "media-123"
        assert http_fb.chamadas[0]["headers"]["Authorization"] == "Bearer fb-token-loja-1"
        assert http_fb.chamadas[0]["url"].endswith("/page-1/feed")
        assert http_ig.chamadas[0]["headers"]["Authorization"] == "Bearer ig-token-loja-1"
        assert http_ig.chamadas[0]["url"].endswith("/ig-1/media")
        assert http_ig.chamadas[1]["url"].endswith("/ig-1/media_publish")


def test_meta_social_control_plane_falha_fechado_sem_homologacao() -> None:
    engine = create_engine("sqlite:///:memory:")
    SecurityBase.metadata.create_all(engine)
    IntegrationConfigBase.metadata.create_all(engine)
    store = ReferenceSecretStore(
        mapping={
            "l1-fb-token": "fb-token-loja-1",
            "l1-fb-secret": "fb-secret-loja-1",
        }
    )
    contexto = _contexto()

    with Session(engine) as session:
        credenciais = ServicoCredenciaisReferenciadas(session, store)
        credenciais.rotacionar(
            contexto=contexto,
            provedor="meta",
            finalidade="social_facebook_access_token",
            nova_referencia="mapping:l1-fb-token",
        )
        credenciais.rotacionar(
            contexto=contexto,
            provedor="meta",
            finalidade="social_facebook_app_secret",
            nova_referencia="mapping:l1-fb-secret",
        )
        _servico(session, store).configurar(
            contexto=contexto,
            configuracao_id="social.facebook--meta",
            servico="social.facebook",
            provedor="meta",
            conta_externa="facebook-principal",
            ambiente=AmbienteIntegracao.HOMOLOGACAO,
            parametros_publicos={"page_id": "page-1", "app_id": "app-1"},
            finalidades_credenciais={
                "access_token": "social_facebook_access_token",
                "app_secret": "social_facebook_app_secret",
            },
            habilitada=True,
            versao_esperada=0,
        )

        with pytest.raises(ErroConfiguracaoServico, match="integracao_nao_homologada"):
            FabricaAdaptersExternos(
                session=session,
                secret_store=store,
            ).meta(
                contexto=contexto,
                configuracao_id="social.facebook--meta",
                http=HTTPMetaCaptura([]),
            )
