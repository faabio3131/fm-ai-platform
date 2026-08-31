"""Persistência mínima auditável de handoff do Assistente de Atendimento."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.seguranca.auditoria import EventoAuditoria, sanitizar_metadata
from core.seguranca.contexto import ContextoExecucao
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy
from infra.seguranca.modelos_orm import EventoAuditoriaORM

_HANDOFF_METADATA_PERMITIDA = frozenset(
    {
        "motivo",
        "cliente_tipo",
        "cliente_ref",
        "historico_count",
        "possui_endereco_salvo",
        "consentimentos_count",
        "ultimo_pedido_id",
        "modalidade",
        "itens_solicitados",
        "itens_resolvidos",
    }
)


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
        metadata_segura: dict[str, str | int | bool] | None = None,
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
                    metadata=sanitizar_metadata(
                        {
                            chave: valor
                            for chave, valor in {
                                "motivo": motivo,
                                **(metadata_segura or {}),
                            }.items()
                            if chave in _HANDOFF_METADATA_PERMITIDA
                        }
                    ),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def ultimo_contexto(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
    ) -> dict[str, str | int | bool] | None:
        db = self._session_factory()
        try:
            row = db.scalar(
                select(EventoAuditoriaORM)
                .where(
                    EventoAuditoriaORM.tenant_id == contexto.tenant_id,
                    EventoAuditoriaORM.unidade_id == contexto.unidade_id,
                    EventoAuditoriaORM.acao == "assistente_atendimento.handoff",
                    EventoAuditoriaORM.recurso_tipo == "conversa_atendimento",
                    EventoAuditoriaORM.recurso_id == conversa_id,
                )
                .order_by(
                    EventoAuditoriaORM.timestamp.desc(),
                    EventoAuditoriaORM.audit_id,
                )
                .limit(1)
            )
            if row is None:
                return None
            return {
                str(chave): valor
                for chave, valor in dict(row.metadata_segura).items()
                if isinstance(valor, (str, int, bool))
            }
        finally:
            db.close()
