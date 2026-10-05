from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import application.campanhas_web as campanhas_app
from application.campanhas_web import despachar_campanha_web, obter_campanha_web
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from core.seguranca.segredos import ReferenceSecretStore
from infra.eventos.modelos_orm import EventBusBase
from infra.gerente_ia.modelos_orm import (
    CoreRuntimeBase,
    EventoCoreORM,
    RascunhoCampanhaORM,
)

AGORA = datetime(2026, 10, 4, 22, 30, tzinfo=timezone.utc)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-organic-app",
        solicitado_em=AGORA,
        origem="tests.wp017-organic-app",
        unidades_permitidas=frozenset({"unidade-1"}),
    )


def _factory(*, canal: str, midia_url: str | None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    CoreRuntimeBase.metadata.create_all(engine)
    EventBusBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            RascunhoCampanhaORM(
                rascunho_id=f"camp-{canal}-1",
                tenant_id="tenant-1",
                unidade_id="unidade-1",
                canal=canal,
                finalidade="promocoes",
                objetivo=f"Publicação {canal}",
                texto_base=f"Conteúdo orgânico {canal}",
                midia_url=midia_url,
                audiencia_elegivel=0,
                criado_em=AGORA,
                criado_por="admin-1",
                correlation_id="corr-create",
                idempotency_key=f"create-{canal}",
                status="publicavel",
            )
        )
        session.add(
            EventoCoreORM(
                event_id=f"evt-publicavel-{canal}",
                tenant_id="tenant-1",
                unidade_id="unidade-1",
                event_type="campanha.publicavel",
                aggregate_id=f"camp-{canal}-1",
                aggregate_type="campanha",
                correlation_id="corr-publishable",
                causation_id=None,
                idempotency_key=f"publishable-{canal}",
                ocorrido_em=AGORA,
                payload_seguro={
                    "campanha_ref": f"campanha://v1/camp-{canal}-1/fingerprint"
                },
                versao=1,
            )
        )
        session.commit()
    return factory


class _AdapterMetaFake:
    def __init__(self) -> None:
        self.facebook_calls: list[dict[str, str]] = []
        self.instagram_calls: list[dict[str, str]] = []

    def publicar_facebook(self, *, mensagem: str, idempotency_key: str) -> str:
        self.facebook_calls.append(
            {"mensagem": mensagem, "idempotency_key": idempotency_key}
        )
        return "fb-post-123"

    def publicar_instagram(
        self,
        *,
        image_url: str,
        legenda: str,
        idempotency_key: str,
    ) -> str:
        self.instagram_calls.append(
            {
                "image_url": image_url,
                "legenda": legenda,
                "idempotency_key": idempotency_key,
            }
        )
        return "ig-media-123"


class _FabricaMetaFake:
    adapter: ClassVar[_AdapterMetaFake] = _AdapterMetaFake()
    config_ids: ClassVar[list[str]] = []

    def __init__(self, *, session, secret_store) -> None:
        del session, secret_store

    def meta(self, *, contexto, configuracao_id: str):
        del contexto
        self.config_ids.append(configuracao_id)
        return self.adapter


@pytest.mark.parametrize(
    ("canal", "midia_url", "config_id", "external_id"),
    (
        ("facebook", None, "social.facebook--meta", "fb-post-123"),
        (
            "instagram",
            "https://example.test/post.jpg",
            "social.instagram--meta",
            "ig-media-123",
        ),
    ),
)
def test_central_web_publica_social_organico_sem_audiencia_crm_e_sem_duplicar(
    monkeypatch,
    canal: str,
    midia_url: str | None,
    config_id: str,
    external_id: str,
) -> None:
    _FabricaMetaFake.adapter = _AdapterMetaFake()
    _FabricaMetaFake.config_ids = []
    monkeypatch.setattr(campanhas_app, "FabricaAdaptersExternos", _FabricaMetaFake)

    factory = _factory(canal=canal, midia_url=midia_url)
    contexto = _contexto()
    campanha = obter_campanha_web(
        session_factory=factory,
        contexto=contexto,
        campanha_id=f"camp-{canal}-1",
    )

    primeiro = despachar_campanha_web(
        session_factory=factory,
        contexto=contexto,
        campanha_id=campanha.campanha_id,
        fingerprint=campanha.fingerprint,
        idempotency_key=f"dispatch-{canal}",
        secret_store_factory=lambda _: ReferenceSecretStore(),
    )
    segundo = despachar_campanha_web(
        session_factory=factory,
        contexto=contexto,
        campanha_id=campanha.campanha_id,
        fingerprint=campanha.fingerprint,
        idempotency_key=f"dispatch-{canal}",
        secret_store_factory=lambda _: ReferenceSecretStore(),
    )

    assert primeiro["canal"] == canal
    assert primeiro["total"] == 1
    assert primeiro["enviados"] == 1
    assert primeiro["resultados"][0]["publicacao_id"] == external_id
    assert primeiro["resultados"][0]["motivo"] == "publicado"
    assert segundo["resultados"][0]["publicacao_id"] == external_id
    assert segundo["resultados"][0]["motivo"] == "idempotente"
    assert _FabricaMetaFake.config_ids == [config_id, config_id]

    if canal == "facebook":
        assert len(_FabricaMetaFake.adapter.facebook_calls) == 1
        assert _FabricaMetaFake.adapter.instagram_calls == []
    else:
        assert len(_FabricaMetaFake.adapter.instagram_calls) == 1
        assert _FabricaMetaFake.adapter.instagram_calls[0]["image_url"] == midia_url
        assert _FabricaMetaFake.adapter.facebook_calls == []
