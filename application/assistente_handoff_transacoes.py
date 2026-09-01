"""Fronteira transacional do handoff do Assistente de Atendimento V1."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao
from infra.assistente_atendimento.handoff_sqlalchemy import HandoffAssistenteAuditSQLAlchemy
from infra.transacoes.uow import UnitOfWorkV1


class HandoffAssistenteTransacionalV1:
    """Mantém persistência infra transaction-neutral e commit na application layer."""

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
        uow = UnitOfWorkV1.adotar_session(db)
        try:
            HandoffAssistenteAuditSQLAlchemy(db).registrar(
                contexto=contexto,
                conversa_id=conversa_id,
                motivo=motivo,
                metadata_segura=metadata_segura,
            )
            uow.commit()
        except Exception:
            uow.rollback()
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
            return HandoffAssistenteAuditSQLAlchemy(db).ultimo_contexto(
                contexto=contexto,
                conversa_id=conversa_id,
            )
        finally:
            db.close()
