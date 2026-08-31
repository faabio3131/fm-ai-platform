"""Persistência mínima auditável de handoff do Assistente de Atendimento."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from core.seguranca.auditoria import EventoAuditoria
from core.seguranca.contexto import ContextoExecucao
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class HandoffAssistenteAuditSQLAlchemy:
    """Registra a transferência sem persistir texto/telefone/PII da conversa."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def registrar(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
        motivo: str,
    ) -> None:
        db = self._session_factory()
        try:
            repo = RepositorioAuditoriaSQLAlchemy(db)
            repo.adicionar(
                EventoAuditoria(
                    audit_id=f"audit-{uuid4().hex}",
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    usuario_id=contexto.usuario_id,
                    papel_efetivo=(
                        min(contexto.papeis, key=lambda item: item.value)
                        if contexto.papeis
                        else None
                    ),
                    acao="assistente_atendimento.handoff",
                    recurso_tipo="conversa_atendimento",
                    recurso_id=conversa_id,
                    resultado="encaminhado",
                    motivo=motivo,
                    correlation_id=contexto.correlation_id,
                    timestamp=datetime.now(timezone.utc),
                    origem="assistente_atendimento_v1",
                    politica="handoff_fail_closed_v1",
                    causation_id=contexto.causation_id,
                    metadata=(("motivo", motivo),),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
