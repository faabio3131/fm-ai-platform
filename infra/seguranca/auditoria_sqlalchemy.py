"""Persistência append-only de eventos de auditoria."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.permissoes import Papel

from .modelos_orm import EventoAuditoriaORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class RepositorioAuditoriaSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def adicionar(self, evento: EventoAuditoria) -> None:
        existente = self._session.get(EventoAuditoriaORM, evento.audit_id)
        if existente is not None:
            return
        self._session.add(
            EventoAuditoriaORM(
                audit_id=evento.audit_id,
                tenant_id=evento.tenant_id,
                unidade_id=evento.unidade_id,
                usuario_id=evento.usuario_id,
                papel_efetivo=evento.papel_efetivo.value if evento.papel_efetivo else None,
                acao=evento.acao,
                recurso_tipo=evento.recurso_tipo,
                recurso_id=evento.recurso_id,
                resultado=evento.resultado,
                motivo=evento.motivo,
                correlation_id=evento.correlation_id,
                timestamp=evento.timestamp,
                origem=evento.origem,
                politica=evento.politica,
                versao=evento.versao,
                causation_id=evento.causation_id,
                antes_resumido=dict(evento.antes_resumido),
                depois_resumido=dict(evento.depois_resumido),
                metadata_segura=dict(evento.metadata),
            )
        )
        self._session.flush()

    def listar(
        self, *, tenant_id: str, unidade_id: str, limite: int = 200
    ) -> tuple[EventoAuditoria, ...]:
        rows = self._session.scalars(
            select(EventoAuditoriaORM)
            .where(
                EventoAuditoriaORM.tenant_id == tenant_id,
                EventoAuditoriaORM.unidade_id == unidade_id,
            )
            .order_by(EventoAuditoriaORM.timestamp.desc(), EventoAuditoriaORM.audit_id)
            .limit(max(1, min(limite, 1000)))
        ).all()
        return tuple(
            EventoAuditoria(
                audit_id=row.audit_id,
                tenant_id=row.tenant_id,
                unidade_id=row.unidade_id,
                usuario_id=row.usuario_id,
                papel_efetivo=Papel(row.papel_efetivo) if row.papel_efetivo else None,
                acao=row.acao,
                recurso_tipo=row.recurso_tipo,
                recurso_id=row.recurso_id,
                resultado=row.resultado,
                motivo=row.motivo,
                correlation_id=row.correlation_id,
                timestamp=_utc(row.timestamp),
                origem=row.origem,
                politica=row.politica,
                versao=row.versao,
                causation_id=row.causation_id,
                antes_resumido=tuple(sorted(dict(row.antes_resumido).items())),
                depois_resumido=tuple(sorted(dict(row.depois_resumido).items())),
                metadata=tuple(sorted(dict(row.metadata_segura).items())),
            )
            for row in rows
        )
