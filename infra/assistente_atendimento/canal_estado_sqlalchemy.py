"""Persistência cifrada da continuidade de canal do Assistente V1."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import insert, select, update
from sqlalchemy.orm import Session

from core.seguranca.contexto import ContextoExecucao

from .canal_schema import assistente_canal_conversas_v1


@dataclass(frozen=True)
class EstadoCanalPersistido:
    conversa_id: str
    estado: str
    recipient: str
    state: dict[str, Any] | None
    pedido_id: str | None
    pagamento_id: str | None
    entrega_id: str | None
    ultimo_inbound_id: str | None
    ultimo_outbound_id: str | None
    ultimo_status_hash: str | None
    versao: int


class EncryptedSQLAlchemyChannelStateStore:
    """Estado mínimo de conversa cifrado e escopado por tenant/unidade."""

    def __init__(self, session: Session, *, master_key: str | None = None) -> None:
        raw = (master_key or os.getenv("FM_AI_SECRET_MASTER_KEY", "")).strip()
        if not raw:
            raise RuntimeError(
                "FM_AI_SECRET_MASTER_KEY ausente; configure a chave mestra da infraestrutura"
            )
        try:
            chave = raw.encode("ascii")
            self._fernet = Fernet(chave)
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("FM_AI_SECRET_MASTER_KEY invalida") from exc
        self._hmac_key = hashlib.sha256(
            b"fm-ai-assistente-channel-v1:" + chave
        ).digest()
        self._session = session

    def sender_hash(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: str,
        recipient: str,
    ) -> str:
        normalizado = "".join(ch for ch in recipient if ch.isdigit())
        if not normalizado:
            raise ValueError("destinatario_canal_invalido")
        material = f"{tenant_id}:{unidade_id}:{canal}:{normalizado}".encode()
        return hmac.new(self._hmac_key, material, hashlib.sha256).hexdigest()

    def _encrypt_text(self, valor: str) -> str:
        return self._fernet.encrypt(valor.encode("utf-8")).decode("ascii")

    def _decrypt_text(self, valor: str) -> str:
        try:
            return self._fernet.decrypt(valor.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise LookupError("estado_canal_nao_pode_ser_decifrado") from exc

    def _encrypt_state(self, state: dict[str, Any] | None) -> str | None:
        if state is None:
            return None
        payload = json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return self._encrypt_text(payload)

    def _decrypt_state(self, ciphertext: str | None) -> dict[str, Any] | None:
        if ciphertext is None:
            return None
        try:
            payload = json.loads(self._decrypt_text(ciphertext))
        except json.JSONDecodeError as exc:
            raise LookupError("estado_canal_invalido") from exc
        if not isinstance(payload, dict):
            raise LookupError("estado_canal_invalido")
        return payload

    def obter(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        recipient: str,
    ) -> EstadoCanalPersistido | None:
        hash_sender = self.sender_hash(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            canal=canal,
            recipient=recipient,
        )
        row = self._session.execute(
            select(assistente_canal_conversas_v1).where(
                assistente_canal_conversas_v1.c.tenant_id == contexto.tenant_id,
                assistente_canal_conversas_v1.c.unidade_id == contexto.unidade_id,
                assistente_canal_conversas_v1.c.canal == canal,
                assistente_canal_conversas_v1.c.sender_hash == hash_sender,
            )
        ).mappings().one_or_none()
        return self._modelo(row) if row is not None else None

    def obter_por_pedido(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
    ) -> tuple[EstadoCanalPersistido, ...]:
        rows = self._session.execute(
            select(assistente_canal_conversas_v1).where(
                assistente_canal_conversas_v1.c.tenant_id == tenant_id,
                assistente_canal_conversas_v1.c.unidade_id == unidade_id,
                assistente_canal_conversas_v1.c.pedido_id == pedido_id,
            )
        ).mappings().all()
        return tuple(self._modelo(row) for row in rows)

    def salvar(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        recipient: str,
        conversa_id: str | None,
        estado: str,
        state: dict[str, Any] | None,
        pedido_id: str | None = None,
        pagamento_id: str | None = None,
        entrega_id: str | None = None,
        ultimo_inbound_id: str | None = None,
        ultimo_outbound_id: str | None = None,
        ultimo_status_hash: str | None = None,
        versao_esperada: int | None = None,
        agora: datetime | None = None,
    ) -> EstadoCanalPersistido:
        instante = agora or datetime.now(timezone.utc)
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("timestamp_canal_sem_timezone")
        instante = instante.astimezone(timezone.utc)
        hash_sender = self.sender_hash(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            canal=canal,
            recipient=recipient,
        )
        existente = self._session.execute(
            select(assistente_canal_conversas_v1).where(
                assistente_canal_conversas_v1.c.tenant_id == contexto.tenant_id,
                assistente_canal_conversas_v1.c.unidade_id == contexto.unidade_id,
                assistente_canal_conversas_v1.c.canal == canal,
                assistente_canal_conversas_v1.c.sender_hash == hash_sender,
            )
        ).mappings().one_or_none()
        if existente is None:
            if versao_esperada not in (None, 0):
                raise RuntimeError("estado_canal_concorrente")
            conversa = conversa_id or str(uuid4())
            self._session.execute(
                insert(assistente_canal_conversas_v1).values(
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    canal=canal,
                    sender_hash=hash_sender,
                    conversa_id=conversa,
                    recipient_ciphertext=self._encrypt_text(recipient),
                    state_ciphertext=self._encrypt_state(state),
                    estado=estado,
                    pedido_id=pedido_id,
                    pagamento_id=pagamento_id,
                    entrega_id=entrega_id,
                    ultimo_inbound_id=ultimo_inbound_id,
                    ultimo_outbound_id=ultimo_outbound_id,
                    ultimo_status_hash=ultimo_status_hash,
                    versao=1,
                    criado_em=instante,
                    atualizado_em=instante,
                )
            )
            self._session.flush()
            atual = self.obter(
                contexto=contexto, canal=canal, recipient=recipient
            )
            if atual is None:
                raise RuntimeError("estado_canal_nao_persistido")
            return atual

        versao_atual = int(existente["versao"])
        if versao_esperada is not None and versao_esperada != versao_atual:
            raise RuntimeError("estado_canal_concorrente")
        conversa = str(existente["conversa_id"])
        if conversa_id is not None and conversa_id != conversa:
            raise RuntimeError("conversa_canal_divergente")
        result = self._session.execute(
            update(assistente_canal_conversas_v1)
            .where(
                assistente_canal_conversas_v1.c.tenant_id == contexto.tenant_id,
                assistente_canal_conversas_v1.c.unidade_id == contexto.unidade_id,
                assistente_canal_conversas_v1.c.canal == canal,
                assistente_canal_conversas_v1.c.sender_hash == hash_sender,
                assistente_canal_conversas_v1.c.versao == versao_atual,
            )
            .values(
                recipient_ciphertext=self._encrypt_text(recipient),
                state_ciphertext=self._encrypt_state(state),
                estado=estado,
                pedido_id=pedido_id,
                pagamento_id=pagamento_id,
                entrega_id=entrega_id,
                ultimo_inbound_id=ultimo_inbound_id,
                ultimo_outbound_id=ultimo_outbound_id,
                ultimo_status_hash=ultimo_status_hash,
                versao=versao_atual + 1,
                atualizado_em=instante,
            )
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("estado_canal_concorrente")
        self._session.flush()
        atual = self.obter(contexto=contexto, canal=canal, recipient=recipient)
        if atual is None:
            raise RuntimeError("estado_canal_nao_persistido")
        return atual

    def registrar_outbound(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        recipient: str,
        outbound_id: str,
        agora: datetime | None = None,
    ) -> EstadoCanalPersistido:
        atual = self.obter(contexto=contexto, canal=canal, recipient=recipient)
        if atual is None:
            raise LookupError("estado_canal_ausente")
        return self.salvar(
            contexto=contexto,
            canal=canal,
            recipient=recipient,
            conversa_id=atual.conversa_id,
            estado=atual.estado,
            state=atual.state,
            pedido_id=atual.pedido_id,
            pagamento_id=atual.pagamento_id,
            entrega_id=atual.entrega_id,
            ultimo_inbound_id=atual.ultimo_inbound_id,
            ultimo_outbound_id=outbound_id,
            ultimo_status_hash=atual.ultimo_status_hash,
            versao_esperada=atual.versao,
            agora=agora,
        )

    def registrar_status_hash(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        recipient: str,
        status_hash: str,
        agora: datetime | None = None,
    ) -> EstadoCanalPersistido:
        atual = self.obter(contexto=contexto, canal=canal, recipient=recipient)
        if atual is None:
            raise LookupError("estado_canal_ausente")
        return self.salvar(
            contexto=contexto,
            canal=canal,
            recipient=recipient,
            conversa_id=atual.conversa_id,
            estado=atual.estado,
            state=atual.state,
            pedido_id=atual.pedido_id,
            pagamento_id=atual.pagamento_id,
            entrega_id=atual.entrega_id,
            ultimo_inbound_id=atual.ultimo_inbound_id,
            ultimo_outbound_id=atual.ultimo_outbound_id,
            ultimo_status_hash=status_hash,
            versao_esperada=atual.versao,
            agora=agora,
        )

    def _modelo(self, row) -> EstadoCanalPersistido:
        return EstadoCanalPersistido(
            conversa_id=str(row["conversa_id"]),
            estado=str(row["estado"]),
            recipient=self._decrypt_text(str(row["recipient_ciphertext"])),
            state=self._decrypt_state(row["state_ciphertext"]),
            pedido_id=str(row["pedido_id"]) if row["pedido_id"] else None,
            pagamento_id=(
                str(row["pagamento_id"]) if row["pagamento_id"] else None
            ),
            entrega_id=str(row["entrega_id"]) if row["entrega_id"] else None,
            ultimo_inbound_id=(
                str(row["ultimo_inbound_id"]) if row["ultimo_inbound_id"] else None
            ),
            ultimo_outbound_id=(
                str(row["ultimo_outbound_id"]) if row["ultimo_outbound_id"] else None
            ),
            ultimo_status_hash=(
                str(row["ultimo_status_hash"]) if row["ultimo_status_hash"] else None
            ),
            versao=int(row["versao"]),
        )
