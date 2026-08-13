from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.erros import ConflitoInbox, DuplicataOutbox
from core.eventos.modelos import (
    ClassificacaoErro,
    DeadLetter,
    EnvelopeMensagem,
    ErroNormalizado,
)
from infra.eventos.adaptador_sqlalchemy import (
    RepositorioDLQSQLAlchemy,
    RepositorioInboxSQLAlchemy,
    RepositorioOutboxSQLAlchemy,
)
from infra.eventos.modelos_orm import EventBusBase


def _message(
    *,
    event_id: str = "evt-1",
    idempotency: str = "idem-1",
    tenant: str = "tenant-1",
    unidade: str = "loja-1",
) -> EnvelopeMensagem:
    return EnvelopeMensagem(
        event_id=EventoId(event_id),
        event_type="pedido.criado",
        aggregate_id="pedido-1",
        aggregate_type="pedido",
        tenant_id=TenantId(tenant),
        unidade_id=UnidadeId(unidade),
        correlation_id=CorrelationId("corr-1"),
        causation_id=None,
        idempotency_key=IdempotencyKey(idempotency),
        occurred_at=datetime.now(timezone.utc),
        payload={"total": "39.90"},
        version=1,
    )


def test_outbox_is_durable_idempotent_and_retryable() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioOutboxSQLAlchemy(session)
        message = _message()
        repo.adicionar(message)
        session.commit()

        loaded = repo.consultar(
            tenant_id=message.tenant_id,
            unidade_id=message.unidade_id,
            event_id=message.event_id,
        )
        assert loaded == message
        assert repo.pendentes(10, datetime.now(timezone.utc)) == (message,)

        retry_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        repo.registrar_falha(
            message.tenant_id,
            message.unidade_id,
            message.event_id,
            erro="timeout",
            proxima_tentativa=retry_at,
        )
        session.commit()
        assert repo.pendentes(10, datetime.now(timezone.utc)) == ()
        assert repo.pendentes(10, retry_at + timedelta(seconds=1)) == (message,)

        repo.marcar_publicada(
            message.tenant_id, message.unidade_id, message.event_id
        )
        session.commit()
        assert repo.pendentes(10, retry_at + timedelta(minutes=1)) == ()


def test_outbox_rejects_duplicate_inside_same_scope() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioOutboxSQLAlchemy(session)
        repo.adicionar(_message())
        with pytest.raises(DuplicataOutbox):
            repo.adicionar(_message(event_id="evt-2", idempotency="idem-1"))
        session.rollback()


def test_same_idempotency_key_is_allowed_for_another_tenant() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioOutboxSQLAlchemy(session)
        first = _message(event_id="evt-1", tenant="tenant-1")
        second = _message(event_id="evt-2", tenant="tenant-2")
        repo.adicionar(first)
        repo.adicionar(second)
        session.commit()
        assert (
            repo.consultar(
                tenant_id=TenantId("tenant-1"),
                unidade_id=UnidadeId("loja-1"),
                idempotency_key=IdempotencyKey("idem-1"),
            )
            == first
        )
        assert (
            repo.consultar(
                tenant_id=TenantId("tenant-2"),
                unidade_id=UnidadeId("loja-1"),
                idempotency_key=IdempotencyKey("idem-1"),
            )
            == second
        )


def test_inbox_distinguishes_duplicate_from_conflict() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioInboxSQLAlchemy(session)
        message = _message()
        assert repo.registrar(message) is True
        session.commit()
        assert repo.registrar(message) is False
        assert (
            repo.ja_processada(
                message.tenant_id, message.unidade_id, message.idempotency_key
            )
            is False
        )
        repo.marcar_processada(
            message.tenant_id, message.unidade_id, message.idempotency_key
        )
        session.commit()
        assert (
            repo.ja_processada(
                message.tenant_id, message.unidade_id, message.idempotency_key
            )
            is True
        )

        with pytest.raises(ConflitoInbox):
            repo.registrar(_message(event_id="evt-other", idempotency="idem-1"))


def test_inbox_same_key_isolated_between_tenants() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    with Session(engine) as session:
        repo = RepositorioInboxSQLAlchemy(session)
        assert repo.registrar(_message(event_id="evt-a", tenant="tenant-a")) is True
        assert repo.registrar(_message(event_id="evt-b", tenant="tenant-b")) is True
        session.commit()


def test_dlq_is_persistent_and_tenant_scoped() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    message = _message()
    dead = DeadLetter.criar(
        message,
        "retry_exhausted",
        ErroNormalizado("TimeoutError", "gateway indisponivel", ClassificacaoErro.RETRYABLE),
        5,
        datetime.now(timezone.utc),
        {"handler": "financeiro"},
    )
    with Session(engine) as session:
        repo = RepositorioDLQSQLAlchemy(session)
        repo.adicionar(dead)
        session.commit()
        items = repo.listar(TenantId("tenant-1"), UnidadeId("loja-1"))
        assert len(items) == 1
        assert items[0].mensagem == message
        assert items[0].tentativas == 5
        assert repo.listar(TenantId("tenant-2"), UnidadeId("loja-1")) == ()
