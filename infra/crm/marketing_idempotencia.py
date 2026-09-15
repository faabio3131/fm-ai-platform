"""Idempotência durável para efeitos externos de marketing CRM.

Reutiliza a Outbox V1 como ledger local do POST Meta. A reserva é persistida em
estado não publicável antes do efeito externo; por desenho, falhas/resultado
incerto não são reenviados automaticamente.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.crm.adapters import PortaEnvioMarketing
from core.crm.erros import ErroCRM
from core.dominio.ids import (
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.eventos.erros import DuplicataOutbox
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.eventos.modelos_orm import OutboxEventoORM

_STATUS_RESERVADO = "external_reserved"
_STATUS_CONCLUIDO = "published"
_EVENT_TYPE = "crm.marketing.whatsapp.dispatch"
_AGGREGATE_TYPE = "crm_cliente"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _digest(valor: str) -> str:
    return hashlib.sha256(valor.encode("utf-8")).hexdigest()


class EnvioMarketingIdempotenteSQLAlchemy:
    """Decorator do transporte que garante at-most-once por chave e escopo."""

    def __init__(
        self,
        *,
        session: Session,
        contexto: ContextoExecucao,
        cliente_id: str,
        texto: str,
        transporte: PortaEnvioMarketing,
    ) -> None:
        if not cliente_id.strip() or not texto.strip():
            raise ValueError("marketing_despacho_invalido")
        self._session = session
        self._contexto = contexto
        self._cliente_id = cliente_id.strip()
        self._conteudo_hash = _digest(texto.strip())
        self._transporte = transporte
        self.acionado = False
        self.enviado = False
        self.motivo = ""
        self.mensagem_id: str | None = None

    def _chave_ledger(self, idempotency_key: str) -> str:
        return f"crm.marketing:{idempotency_key.strip()}"

    def _existente(self, chave_ledger: str) -> OutboxEventoORM | None:
        return self._session.scalar(
            select(OutboxEventoORM).where(
                OutboxEventoORM.tenant_id == self._contexto.tenant_id,
                OutboxEventoORM.unidade_id == self._contexto.unidade_id,
                OutboxEventoORM.idempotency_key == chave_ledger,
            )
        )

    def _payload(
        self,
        *,
        campanha_ref: str,
        idempotency_key: str,
        mensagem_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cliente_id": self._cliente_id,
            "campanha_ref": campanha_ref,
            "canal": "whatsapp",
            "conteudo_sha256": self._conteudo_hash,
            "transport_idempotency_key": idempotency_key,
        }
        if mensagem_id:
            payload["mensagem_id"] = mensagem_id
        return payload

    def _validar_semantica(
        self,
        row: OutboxEventoORM,
        *,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        esperado = self._payload(
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
        )
        existente = dict(row.payload)
        for chave, valor in esperado.items():
            if existente.get(chave) != valor:
                raise ErroCRM("conflito_idempotencia_marketing")

    def _aplicar_replay(self, row: OutboxEventoORM) -> None:
        payload = dict(row.payload)
        mensagem_id = payload.get("mensagem_id")
        if row.status == _STATUS_CONCLUIDO:
            self.enviado = True
            self.motivo = "idempotente"
            self.mensagem_id = (
                mensagem_id if isinstance(mensagem_id, str) and mensagem_id else None
            )
            return
        self.enviado = False
        self.motivo = "marketing_despacho_ja_reservado"
        self.mensagem_id = None

    def _reservar(
        self,
        *,
        campanha_ref: str,
        idempotency_key: str,
    ) -> OutboxEventoORM | None:
        chave_ledger = self._chave_ledger(idempotency_key)
        existente = self._existente(chave_ledger)
        if existente is not None:
            self._validar_semantica(
                existente,
                campanha_ref=campanha_ref,
                idempotency_key=idempotency_key,
            )
            return existente

        digest = _digest(
            f"{self._contexto.tenant_id}:{self._contexto.unidade_id}:{chave_ledger}"
        )
        mensagem = EnvelopeMensagem(
            event_id=EventoId.de(f"mkt_{digest[:24]}"),
            event_type=_EVENT_TYPE,
            aggregate_id=self._cliente_id,
            aggregate_type=_AGGREGATE_TYPE,
            tenant_id=TenantId.de(self._contexto.tenant_id),
            unidade_id=UnidadeId.de(self._contexto.unidade_id),
            correlation_id=CorrelationId.de(self._contexto.correlation_id),
            causation_id=None,
            idempotency_key=IdempotencyKey.de(chave_ledger),
            occurred_at=_agora(),
            payload=self._payload(
                campanha_ref=campanha_ref,
                idempotency_key=idempotency_key,
            ),
        )
        try:
            RepositorioOutboxSQLAlchemy(self._session).adicionar(mensagem)
            self._session.execute(
                update(OutboxEventoORM)
                .where(OutboxEventoORM.event_id == str(mensagem.event_id))
                .values(status=_STATUS_RESERVADO)
            )
            self._session.commit()
            return None
        except DuplicataOutbox:
            self._session.rollback()
            existente = self._existente(chave_ledger)
            if existente is None:
                raise ErroCRM("conflito_idempotencia_marketing")
            self._validar_semantica(
                existente,
                campanha_ref=campanha_ref,
                idempotency_key=idempotency_key,
            )
            return existente

    def _concluir(
        self,
        *,
        campanha_ref: str,
        idempotency_key: str,
        mensagem_id: str | None,
    ) -> None:
        chave_ledger = self._chave_ledger(idempotency_key)
        payload = self._payload(
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
            mensagem_id=mensagem_id,
        )
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
                payload=payload,
            )
        )
        if getattr(resultado, "rowcount", 0) != 1:
            self._session.rollback()
            raise ErroCRM("marketing_despacho_reserva_perdida")
        self._session.commit()

    def enviar(
        self,
        *,
        referencia_contato: str,
        campanha_ref: str,
        idempotency_key: str,
    ) -> None:
        self.acionado = True
        existente = self._reservar(
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
        )
        if existente is not None:
            self._aplicar_replay(existente)
            return

        try:
            self._transporte.enviar(
                referencia_contato=referencia_contato,
                campanha_ref=campanha_ref,
                idempotency_key=idempotency_key,
            )
        except Exception:
            self._session.rollback()
            raise

        mensagem_id = getattr(self._transporte, "mensagem_id", None)
        mensagem_id_segura = (
            mensagem_id if isinstance(mensagem_id, str) and mensagem_id.strip() else None
        )
        self._concluir(
            campanha_ref=campanha_ref,
            idempotency_key=idempotency_key,
            mensagem_id=mensagem_id_segura,
        )
        self.enviado = True
        self.motivo = "enviado"
        self.mensagem_id = mensagem_id_segura
