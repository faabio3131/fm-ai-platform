"""Persistência governada do ciclo humano de campanhas F4-G."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.gerente_ia.erros import ErroGerenteIA
from core.gerente_ia.modelos import (
    CampanhaAprovada,
    CampanhaPublicavel,
    CampanhaRef,
    fingerprint_campanha,
)
from infra.gerente_ia.modelos_orm import EventoCoreORM, RascunhoCampanhaORM
from infra.gerente_ia.persistencia_sqlalchemy import CampanhasGerenciaisSQLAlchemy


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


class CampanhasGovernadasSQLAlchemy(CampanhasGerenciaisSQLAlchemy):
    """Reusa o rascunho canônico e acrescenta apenas transições humanas."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self._session_governada = session

    def _row(
        self, *, tenant_id: str, unidade_id: str, campanha_id: str
    ) -> RascunhoCampanhaORM:
        row = self._session_governada.scalar(
            select(RascunhoCampanhaORM).where(
                RascunhoCampanhaORM.rascunho_id == campanha_id,
                RascunhoCampanhaORM.tenant_id == tenant_id,
                RascunhoCampanhaORM.unidade_id == unidade_id,
            )
        )
        if row is None:
            raise ErroGerenteIA("recurso_indisponivel")
        return row

    @staticmethod
    def _fingerprint(row: RascunhoCampanhaORM) -> str:
        return fingerprint_campanha(
            campanha_id=row.rascunho_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            canal=row.canal,
            finalidade=row.finalidade,
            objetivo=row.objetivo,
            texto_base=row.texto_base,
            audiencia_elegivel=row.audiencia_elegivel,
        )

    def _evento_idempotente(
        self, *, tenant_id: str, unidade_id: str, idempotency_key: str
    ) -> EventoCoreORM | None:
        return self._session_governada.scalar(
            select(EventoCoreORM).where(
                EventoCoreORM.tenant_id == tenant_id,
                EventoCoreORM.unidade_id == unidade_id,
                EventoCoreORM.idempotency_key == idempotency_key,
            )
        )

    def _registrar_transicao(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        event_type: str,
        correlation_id: str,
        idempotency_key: str,
        ocorrido_em: datetime,
        payload: dict[str, Any],
        versao: int,
    ) -> None:
        self._session_governada.add(
            EventoCoreORM(
                event_id=f"evt_{uuid4().hex}",
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                event_type=event_type,
                aggregate_id=campanha_id,
                aggregate_type="campanha",
                correlation_id=correlation_id,
                causation_id=None,
                idempotency_key=idempotency_key,
                ocorrido_em=ocorrido_em,
                payload_seguro=payload,
                versao=versao,
            )
        )

    def aprovar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> CampanhaAprovada:
        evento = self._evento_idempotente(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            idempotency_key=idempotency_key,
        )
        if evento is not None:
            if (
                evento.event_type != "campanha.aprovada"
                or evento.aggregate_id != campanha_id
            ):
                raise ErroGerenteIA("conflito_idempotencia")
            payload = dict(evento.payload_seguro)
            return CampanhaAprovada(
                campanha_id=campanha_id,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                fingerprint=str(payload["fingerprint"]),
                aprovado_por=str(payload["aprovado_por"]),
                aprovado_em=_utc(evento.ocorrido_em),
                idempotency_key=idempotency_key,
                idempotente=True,
            )

        row = self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        if row.status != "rascunho":
            raise ErroGerenteIA("campanha_nao_esta_em_rascunho")
        fingerprint = self._fingerprint(row)
        row.status = "aprovada"
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.aprovada",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "fingerprint": fingerprint,
                "aprovado_por": usuario_id,
            },
            versao=1,
        )
        self._session_governada.flush()
        return CampanhaAprovada(
            campanha_id=campanha_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            fingerprint=fingerprint,
            aprovado_por=usuario_id,
            aprovado_em=agora,
            idempotency_key=idempotency_key,
        )

    def publicar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        campanha_id: str,
        usuario_id: str,
        correlation_id: str,
        idempotency_key: str,
        agora: datetime,
    ) -> CampanhaPublicavel:
        evento = self._evento_idempotente(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            idempotency_key=idempotency_key,
        )
        if evento is not None:
            if (
                evento.event_type != "campanha.publicavel"
                or evento.aggregate_id != campanha_id
            ):
                raise ErroGerenteIA("conflito_idempotencia")
            payload = dict(evento.payload_seguro)
            return CampanhaPublicavel(
                campanha_id=campanha_id,
                tenant_id=tenant_id,
                unidade_id=unidade_id,
                fingerprint=str(payload["fingerprint"]),
                campanha_ref=CampanhaRef(str(payload["campanha_ref"])),
                publicado_por=str(payload["publicado_por"]),
                publicado_em=_utc(evento.ocorrido_em),
                idempotency_key=idempotency_key,
                idempotente=True,
            )

        row = self._row(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
        )
        if row.status != "aprovada":
            raise ErroGerenteIA("campanha_nao_esta_aprovada")
        fingerprint = self._fingerprint(row)
        aprovacao = self._session_governada.scalar(
            select(EventoCoreORM)
            .where(
                EventoCoreORM.tenant_id == tenant_id,
                EventoCoreORM.unidade_id == unidade_id,
                EventoCoreORM.aggregate_type == "campanha",
                EventoCoreORM.aggregate_id == campanha_id,
                EventoCoreORM.event_type == "campanha.aprovada",
            )
            .order_by(EventoCoreORM.ocorrido_em.desc())
            .limit(1)
        )
        if aprovacao is None:
            raise ErroGerenteIA("campanha_aprovacao_inconsistente")
        aprovado_fingerprint = str(
            dict(aprovacao.payload_seguro).get("fingerprint", "")
        )
        if aprovado_fingerprint != fingerprint:
            raise ErroGerenteIA("campanha_alterada_apos_aprovacao")

        campanha_ref = CampanhaRef.de_publicacao(
            campanha_id=campanha_id,
            fingerprint=fingerprint,
        )
        row.status = "publicavel"
        self._registrar_transicao(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            campanha_id=campanha_id,
            event_type="campanha.publicavel",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            ocorrido_em=agora,
            payload={
                "campanha_id": campanha_id,
                "campanha_ref": str(campanha_ref),
                "fingerprint": fingerprint,
                "publicado_por": usuario_id,
            },
            versao=2,
        )
        self._session_governada.flush()
        return CampanhaPublicavel(
            campanha_id=campanha_id,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            fingerprint=fingerprint,
            campanha_ref=campanha_ref,
            publicado_por=usuario_id,
            publicado_em=agora,
            idempotency_key=idempotency_key,
        )
