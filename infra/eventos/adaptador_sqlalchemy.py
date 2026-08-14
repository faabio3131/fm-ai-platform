"""Repositorios SQLAlchemy duráveis para Outbox, Inbox e DLQ."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import cast

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.dominio.ids import (
    CausationId,
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

from .modelos_orm import DeadLetterEventoORM, InboxEventoORM, OutboxEventoORM


def _utc(value: object) -> datetime:
    dt = cast(datetime, value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _envelope(
    row: OutboxEventoORM | InboxEventoORM | DeadLetterEventoORM,
) -> EnvelopeMensagem:
    return EnvelopeMensagem(
        event_id=EventoId(row.event_id),
        event_type=row.event_type,
        aggregate_id=row.aggregate_id,
        aggregate_type=row.aggregate_type,
        tenant_id=TenantId(row.tenant_id),
        unidade_id=UnidadeId(row.unidade_id),
        correlation_id=CorrelationId(row.correlation_id),
        causation_id=CausationId(row.causation_id) if row.causation_id else None,
        idempotency_key=IdempotencyKey(row.idempotency_key),
        occurred_at=_utc(row.occurred_at),
        payload=dict(row.payload),
        version=row.version,
    )


class RepositorioOutboxSQLAlchemy:
    """Outbox transacional; commit pertence ao Unit of Work chamador."""

    def __init__(
        self,
        session: Session,
        *,
        ao_adicionar: Callable[[EnvelopeMensagem], object] | None = None,
    ) -> None:
        self._session = session
        self._ao_adicionar = ao_adicionar

    def adicionar(self, mensagem: EnvelopeMensagem) -> None:
        existente = self._session.scalar(
            select(OutboxEventoORM).where(
                or_(
                    OutboxEventoORM.event_id == str(mensagem.event_id),
                    (
                        (OutboxEventoORM.tenant_id == str(mensagem.tenant_id))
                        & (OutboxEventoORM.unidade_id == str(mensagem.unidade_id))
                        & (
                            OutboxEventoORM.idempotency_key
                            == str(mensagem.idempotency_key)
                        )
                    ),
                )
            )
        )
        if existente is not None:
            raise DuplicataOutbox()
        self._session.add(
            OutboxEventoORM(
                event_id=str(mensagem.event_id),
                event_type=mensagem.event_type,
                aggregate_id=mensagem.aggregate_id,
                aggregate_type=mensagem.aggregate_type,
                tenant_id=str(mensagem.tenant_id),
                unidade_id=str(mensagem.unidade_id),
                correlation_id=str(mensagem.correlation_id),
                causation_id=str(mensagem.causation_id) if mensagem.causation_id else None,
                idempotency_key=str(mensagem.idempotency_key),
                occurred_at=mensagem.occurred_at,
                payload=dict(mensagem.payload),
                version=mensagem.version,
                status="pending",
                attempts=0,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise DuplicataOutbox() from exc
        if self._ao_adicionar is not None:
            self._ao_adicionar(mensagem)

    def consultar(
        self,
        *,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        event_id: EventoId | None = None,
        idempotency_key: IdempotencyKey | None = None,
    ) -> EnvelopeMensagem | None:
        if event_id is None and idempotency_key is None:
            raise ValueError("event_id ou idempotency_key obrigatorio")
        predicates = [
            OutboxEventoORM.tenant_id == str(tenant_id),
            OutboxEventoORM.unidade_id == str(unidade_id),
        ]
        if event_id is not None:
            predicates.append(OutboxEventoORM.event_id == str(event_id))
        if idempotency_key is not None:
            predicates.append(
                OutboxEventoORM.idempotency_key == str(idempotency_key)
            )
        row = self._session.scalar(select(OutboxEventoORM).where(*predicates))
        return _envelope(row) if row else None

    def pendentes(self, limite: int, agora: datetime) -> tuple[EnvelopeMensagem, ...]:
        if limite < 1:
            return ()
        instant = agora.astimezone(timezone.utc)
        rows = self._session.scalars(
            select(OutboxEventoORM)
            .where(
                OutboxEventoORM.status.in_(("pending", "retry")),
                or_(
                    OutboxEventoORM.next_attempt_at.is_(None),
                    OutboxEventoORM.next_attempt_at <= instant,
                ),
            )
            .order_by(OutboxEventoORM.occurred_at, OutboxEventoORM.event_id)
            .limit(limite)
        ).all()
        return tuple(_envelope(row) for row in rows)

    def marcar_publicada(
        self, tenant_id: TenantId, unidade_id: UnidadeId, event_id: EventoId
    ) -> None:
        now = datetime.now(timezone.utc)
        result = self._session.execute(
            update(OutboxEventoORM)
            .where(
                OutboxEventoORM.tenant_id == str(tenant_id),
                OutboxEventoORM.unidade_id == str(unidade_id),
                OutboxEventoORM.event_id == str(event_id),
            )
            .values(status="published", published_at=now, next_attempt_at=None)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise KeyError(str(event_id))
        self._session.flush()

    def registrar_falha(
        self,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        event_id: EventoId,
        *,
        erro: str,
        proxima_tentativa: datetime,
    ) -> None:
        row = self._session.scalar(
            select(OutboxEventoORM).where(
                OutboxEventoORM.tenant_id == str(tenant_id),
                OutboxEventoORM.unidade_id == str(unidade_id),
                OutboxEventoORM.event_id == str(event_id),
            )
        )
        if row is None:
            raise KeyError(str(event_id))
        row.status = "retry"
        row.attempts += 1
        row.last_error = erro[:4000]
        row.next_attempt_at = proxima_tentativa.astimezone(timezone.utc)
        self._session.flush()


class RepositorioInboxSQLAlchemy:
    """Inbox idempotente para consumidores de eventos."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _pk(
        tenant_id: TenantId, unidade_id: UnidadeId, idempotency_key: IdempotencyKey
    ) -> tuple[str, str, str]:
        return str(tenant_id), str(unidade_id), str(idempotency_key)

    def registrar(self, mensagem: EnvelopeMensagem) -> bool:
        key = self._pk(
            mensagem.tenant_id, mensagem.unidade_id, mensagem.idempotency_key
        )
        existente = self._session.get(InboxEventoORM, key)
        if existente is not None:
            if existente.event_id != str(mensagem.event_id):
                raise ConflitoInbox()
            return False
        self._session.add(
            InboxEventoORM(
                tenant_id=str(mensagem.tenant_id),
                unidade_id=str(mensagem.unidade_id),
                idempotency_key=str(mensagem.idempotency_key),
                event_id=str(mensagem.event_id),
                event_type=mensagem.event_type,
                aggregate_id=mensagem.aggregate_id,
                aggregate_type=mensagem.aggregate_type,
                correlation_id=str(mensagem.correlation_id),
                causation_id=str(mensagem.causation_id) if mensagem.causation_id else None,
                occurred_at=mensagem.occurred_at,
                payload=dict(mensagem.payload),
                version=mensagem.version,
                processed=False,
                attempts=0,
            )
        )
        try:
            self._session.flush()
        except IntegrityError as exc:
            raise ConflitoInbox() from exc
        return True

    def ja_processada(
        self,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        idempotency_key: IdempotencyKey,
    ) -> bool:
        row = self._session.get(
            InboxEventoORM, self._pk(tenant_id, unidade_id, idempotency_key)
        )
        return bool(row and row.processed)

    def marcar_processada(
        self,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        idempotency_key: IdempotencyKey,
    ) -> None:
        row = self._session.get(
            InboxEventoORM, self._pk(tenant_id, unidade_id, idempotency_key)
        )
        if row is None:
            raise KeyError(str(idempotency_key))
        row.processed = True
        row.attempts += 1
        row.processed_at = datetime.now(timezone.utc)
        self._session.flush()


class RepositorioDLQSQLAlchemy:
    """Dead-letter queue persistente e escopada por tenant/unidade."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def adicionar(self, item: DeadLetter) -> None:
        message = item.mensagem
        existing = self._session.get(DeadLetterEventoORM, str(message.event_id))
        if existing is not None:
            if (
                existing.tenant_id != str(message.tenant_id)
                or existing.unidade_id != str(message.unidade_id)
            ):
                raise ValueError("event_id de outra unidade")
            return
        self._session.add(
            DeadLetterEventoORM(
                event_id=str(message.event_id),
                event_type=message.event_type,
                aggregate_id=message.aggregate_id,
                aggregate_type=message.aggregate_type,
                tenant_id=str(message.tenant_id),
                unidade_id=str(message.unidade_id),
                correlation_id=str(message.correlation_id),
                causation_id=str(message.causation_id) if message.causation_id else None,
                idempotency_key=str(message.idempotency_key),
                occurred_at=message.occurred_at,
                payload=dict(message.payload),
                version=message.version,
                motivo=item.motivo,
                erro_tipo=item.ultimo_erro.tipo,
                erro_mensagem=item.ultimo_erro.mensagem,
                erro_classificacao=item.ultimo_erro.classificacao.value,
                tentativas=item.tentativas,
                metadata_segura=dict(item.metadata),
                created_at=item.timestamp,
            )
        )
        self._session.flush()

    def listar(
        self, tenant_id: TenantId, unidade_id: UnidadeId
    ) -> tuple[DeadLetter, ...]:
        rows = self._session.scalars(
            select(DeadLetterEventoORM)
            .where(
                DeadLetterEventoORM.tenant_id == str(tenant_id),
                DeadLetterEventoORM.unidade_id == str(unidade_id),
            )
            .order_by(DeadLetterEventoORM.created_at.desc())
        ).all()
        return tuple(
            DeadLetter(
                mensagem=_envelope(row),
                motivo=row.motivo,
                ultimo_erro=ErroNormalizado(
                    row.erro_tipo,
                    row.erro_mensagem,
                    ClassificacaoErro(row.erro_classificacao),
                ),
                tentativas=row.tentativas,
                timestamp=_utc(row.created_at),
                tenant_id=TenantId(row.tenant_id),
                unidade_id=UnidadeId(row.unidade_id),
                correlation_id=CorrelationId(row.correlation_id),
                metadata=tuple(sorted(dict(row.metadata_segura).items())),
            )
            for row in rows
        )
