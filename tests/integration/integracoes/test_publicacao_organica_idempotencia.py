from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.gerente_ia.erros import ErroGerenteIA
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Papel, Permissao
from infra.eventos.modelos_orm import EventBusBase
from infra.integracoes.publicacao_organica_idempotencia import (
    PublicacaoOrganicaIdempotenteSQLAlchemy,
)

AGORA = datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc)


def _contexto() -> ContextoExecucao:
    return ContextoExecucao(
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        usuario_id="admin-1",
        papeis=frozenset({Papel.ADMINISTRADOR}),
        permissoes=frozenset(Permissao),
        correlation_id="corr-organic",
        solicitado_em=AGORA,
        origem="tests.wp017-organic-ledger",
        unidades_permitidas=frozenset({"unidade-1"}),
    )


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_publicacao_organica_replay_nao_repete_post_externo() -> None:
    factory = _factory()
    chamadas: list[str] = []

    def publicar() -> str:
        chamadas.append("post")
        return "post-123"

    with factory() as session:
        ledger = PublicacaoOrganicaIdempotenteSQLAlchemy(
            session=session,
            contexto=_contexto(),
            campanha_id="camp-fb-1",
            campanha_ref="campanha://v1/camp-fb-1/fingerprint",
            canal="facebook",
            texto="Oferta orgânica",
            midia_url=None,
            persistir=session.commit,
            reverter=session.rollback,
        )
        external_id, motivo = ledger.executar(
            idempotency_key="organic-fb-1",
            publicar=publicar,
        )
        assert (external_id, motivo) == ("post-123", "publicado")

    with factory() as session:
        replay = PublicacaoOrganicaIdempotenteSQLAlchemy(
            session=session,
            contexto=_contexto(),
            campanha_id="camp-fb-1",
            campanha_ref="campanha://v1/camp-fb-1/fingerprint",
            canal="facebook",
            texto="Oferta orgânica",
            midia_url=None,
            persistir=session.commit,
            reverter=session.rollback,
        )
        external_id, motivo = replay.executar(
            idempotency_key="organic-fb-1",
            publicar=publicar,
        )
        assert (external_id, motivo) == ("post-123", "idempotente")

    assert chamadas == ["post"]


def test_publicacao_organica_resultado_incerto_bloqueia_retry_cego() -> None:
    factory = _factory()
    chamadas: list[str] = []

    def timeout_depois_do_post() -> str:
        chamadas.append("primeiro")
        raise TimeoutError("resultado externo incerto")

    with factory() as session:
        ledger = PublicacaoOrganicaIdempotenteSQLAlchemy(
            session=session,
            contexto=_contexto(),
            campanha_id="camp-ig-1",
            campanha_ref="campanha://v1/camp-ig-1/fingerprint",
            canal="instagram",
            texto="Legenda orgânica",
            midia_url="https://example.test/post.jpg",
            persistir=session.commit,
            reverter=session.rollback,
        )
        with pytest.raises(TimeoutError):
            ledger.executar(
                idempotency_key="organic-ig-1",
                publicar=timeout_depois_do_post,
            )

    def segundo_post() -> str:
        chamadas.append("segundo")
        return "media-duplicada"

    with factory() as session:
        replay = PublicacaoOrganicaIdempotenteSQLAlchemy(
            session=session,
            contexto=_contexto(),
            campanha_id="camp-ig-1",
            campanha_ref="campanha://v1/camp-ig-1/fingerprint",
            canal="instagram",
            texto="Legenda orgânica",
            midia_url="https://example.test/post.jpg",
            persistir=session.commit,
            reverter=session.rollback,
        )
        with pytest.raises(ErroGerenteIA) as excinfo:
            replay.executar(
                idempotency_key="organic-ig-1",
                publicar=segundo_post,
            )
        assert excinfo.value.codigo == "campanha_publicacao_externa_incerta"

    assert chamadas == ["primeiro"]
