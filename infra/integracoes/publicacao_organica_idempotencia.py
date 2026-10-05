"""Idempotência durável para publicações orgânicas externas do WP-017.

Reutiliza a Outbox V1 como ledger local antes de chamar a Meta Graph API. Uma
reserva confirmada nunca é reenviada automaticamente quando o resultado externo
ficou incerto, evitando duplicação de posts.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.erros import DuplicataOutbox
from core.eventos.modelos import EnvelopeMensagem
from core.gerente_ia.erros import ErroGerenteIA
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.eventos.modelos_orm import OutboxEventoORM

_STATUS_RESERVADO = "external_reserved"
_STATUS_CONCLUIDO = "published"
_AGGREGATE_TYPE = "campanha"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _digest(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


class PublicacaoOrganicaIdempotenteSQLAlchemy:
    """Protege Facebook/Instagram contra repetição cega de POST externo."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        campanha_id: str,
        campanha_ref: str,
        canal: str,
        texto: str,
        midia_url: str | None,
        persistir: Callable[[], None],
        reverter: Callable[[], None],
    ) -> None:
        canal_normalizado = canal.strip().casefold()
        if canal_normalizado not in {"facebook", "instagram"}:
            raise ValueError("canal_organico_nao_suportado")
        if not campanha_id.strip() or not campanha_ref.strip() or not texto.strip():
            raise ValueError("publicacao_organica_invalida")
        self._session = session
        self._contexto = contexto
        self._campanha_id = campanha_id.strip()
        self._campanha_ref = campanha_ref.strip()
        self._canal = canal_normalizado
        self._conteudo_hash = _digest(texto.strip())
        self._midia_hash = _digest(midia_url.strip()) if midia_url and midia_url.strip() else None
        self._persistir = persistir
        self._reverter = reverter

    def _chave_ledger(self, idempotency_key: str) -> str:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key_obrigatoria")
        return f"marketing.organic:{key}"

    def _payload(
        self,
        *,
        idempotency_key: str,
        publicacao_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "campanha_id": self._campanha_id,
            "campanha_ref": self._campanha_ref,
            "canal": self._canal,
            "conteudo_sha256": self._conteudo_hash,
            "transport_idempotency_key": idempotency_key,
        }
        if self._midia_hash:
            payload["midia_sha256"] = self._midia_hash
        if publicacao_id:
            payload["publicacao_id"] = publicacao_id
        return payload

    def _existente(self, chave_ledger: str) -> OutboxEventoORM | None:
        return self._session.scalar(
            select(OutboxEventoORM).where(
                OutboxEventoORM.tenant_id == self._contexto.tenant_id,
                OutboxEventoORM.unidade_id == self._contexto.unidade_id,
                OutboxEventoORM.idempotency_key == chave_ledger,
            )
        )

    def _validar_semantica(
        self,
        row: OutboxEventoORM,
        *,
        idempotency_key: str,
    ) -> None:
        esperado = self._payload(idempotency_key=idempotency_key)
        existente = dict(row.payload)
        for chave, valor in esperado.items():
            if existente.get(chave) != valor:
                raise ErroGerenteIA("conflito_idempotencia")

    def _reservar(self, *, idempotency_key: str) -> OutboxEventoORM | None:
        chave_ledger = self._chave_ledger(idempotency_key)
        existente = self._existente(chave_ledger)
        if existente is not None:
            self._validar_semantica(existente, idempotency_key=idempotency_key)
            return existente

        digest = _digest(
            f"{self._contexto.tenant_id}:{self._contexto.unidade_id}:{chave_ledger}"
        )
        mensagem = EnvelopeMensagem(
            event_id=EventoId.de(f"org_{digest[:24]}"),
            event_type=f"marketing.organic.{self._canal}.publish",
            aggregate_id=self._campanha_id,
            aggregate_type=_AGGREGATE_TYPE,
            tenant_id=TenantId.de(self._contexto.tenant_id),
            unidade_id=UnidadeId.de(self._contexto.unidade_id),
            correlation_id=CorrelationId.de(self._contexto.correlation_id),
            causation_id=None,
            idempotency_key=IdempotencyKey.de(chave_ledger),
            occurred_at=_agora(),
            payload=self._payload(idempotency_key=idempotency_key),
        )
        try:
            RepositorioOutboxSQLAlchemy(self._session).adicionar(mensagem)
            self._session.execute(
                update(OutboxEventoORM)
                .where(OutboxEventoORM.event_id == str(mensagem.event_id))
                .values(status=_STATUS_RESERVADO)
            )
            self._persistir()
            return None
        except DuplicataOutbox:
            self._reverter()
            existente = self._existente(chave_ledger)
            if existente is None:
                raise ErroGerenteIA("conflito_idempotencia")
            self._validar_semantica(existente, idempotency_key=idempotency_key)
            return existente

    def _concluir(self, *, idempotency_key: str, publicacao_id: str) -> None:
        chave_ledger = self._chave_ledger(idempotency_key)
        resultado = self._session.execute(
            update(OutboxEventoORM)
            .where(
                OutboxEventoORM.tenant_id == self._contexto.tenant_id,
                OutboxEventoORM.unidade_id == self._contexto.unidade_id,
                OutboxEventoORM.idempotency_key == chave_ledger,
                OutboxEventoORM.status == _STATUS_RESERVADO,
            )
            .values(
                status=_STATUS_CONCLUIDO,
                published_at=_agora(),
                payload=self._payload(
                    idempotency_key=idempotency_key,
                    publicacao_id=publicacao_id,
                ),
            )
        )
        if getattr(resultado, "rowcount", 0) != 1:
            self._reverter()
            raise ErroGerenteIA("campanha_publicacao_reserva_perdida")
        self._persistir()

    def executar(
        self,
        *,
        idempotency_key: str,
        publicar: Callable[[], str],
    ) -> tuple[str, str]:
        existente = self._reservar(idempotency_key=idempotency_key)
        if existente is not None:
            payload = dict(existente.payload)
            if existente.status == _STATUS_CONCLUIDO:
                publicacao_id = str(payload.get("publicacao_id", "")).strip()
                if not publicacao_id:
                    raise ErroGerenteIA("campanha_publicacao_inconsistente")
                return publicacao_id, "idempotente"
            raise ErroGerenteIA("campanha_publicacao_externa_incerta")

        try:
            publicacao_id = str(publicar()).strip()
        except Exception:
            self._reverter()
            raise
        if not publicacao_id:
            self._reverter()
            raise ErroGerenteIA("campanha_publicacao_sem_id_externo")
        self._concluir(
            idempotency_key=idempotency_key,
            publicacao_id=publicacao_id,
        )
        return publicacao_id, "publicado"
