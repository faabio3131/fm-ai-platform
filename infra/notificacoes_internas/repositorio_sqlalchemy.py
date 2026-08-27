"""Diretório SQLAlchemy tenant-safe com contato cifrado."""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.notificacoes_internas.modelos import (
    CanalNotificacaoInterna,
    DestinatarioNotificacaoInterna,
)
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.segredos import SecretValue

from .modelos_orm import DestinatarioNotificacaoInternaORM


def _normalizar_whatsapp(valor: str) -> str:
    digits = "".join(ch for ch in valor if ch.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("contato WhatsApp invalido")
    return digits


def _mascara_whatsapp(valor: str) -> str:
    return f"***{valor[-4:]}"


class RepositorioNotificacoesInternasSQLAlchemy:
    def __init__(
        self,
        session: Session,
        *,
        master_key: str | None = None,
    ) -> None:
        raw = (
            master_key
            if master_key is not None
            else os.getenv("FM_AI_SECRET_MASTER_KEY", "")
        )
        chave = (raw or "").strip()
        if not chave:
            raise RuntimeError(
                "FM_AI_SECRET_MASTER_KEY ausente para contatos internos"
            )
        try:
            self._fernet = Fernet(chave.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("FM_AI_SECRET_MASTER_KEY invalida") from exc
        self._fingerprint_key = chave.encode("ascii")
        self._session = session

    @staticmethod
    def _dominio(
        row: DestinatarioNotificacaoInternaORM,
    ) -> DestinatarioNotificacaoInterna:
        return DestinatarioNotificacaoInterna(
            destinatario_id=row.destinatario_id,
            tenant_id=row.tenant_id,
            unidade_id=row.unidade_id,
            nome_exibicao=row.nome_exibicao,
            cargo=row.cargo,
            canal=CanalNotificacaoInterna(row.canal),
            referencia_contato=row.referencia_contato,
            contato_mascara=row.contato_mascara,
            receber_alertas_estoque=bool(row.receber_alertas_estoque),
            ativo=bool(row.ativo),
            versao=row.versao,
        )

    def _fingerprint(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        canal: CanalNotificacaoInterna,
        contato: str,
    ) -> str:
        payload = (
            f"{tenant_id}:{unidade_id}:{canal.value}:{contato}"
        ).encode("utf-8")
        return hmac.new(
            self._fingerprint_key,
            payload,
            hashlib.sha256,
        ).hexdigest()

    def configurar(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        nome_exibicao: str,
        cargo: str | None,
        canal: CanalNotificacaoInterna,
        contato: SecretValue,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna:
        identificador = destinatario_id.strip()
        nome = nome_exibicao.strip()
        if not identificador or not nome:
            raise ValueError("destinatario e nome sao obrigatorios")
        if canal is not CanalNotificacaoInterna.WHATSAPP:
            raise ValueError("canal interno nao suportado")

        normalizado = _normalizar_whatsapp(contato.reveal())
        fingerprint = self._fingerprint(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            canal=canal,
            contato=normalizado,
        )
        conflito = self._session.scalar(
            select(DestinatarioNotificacaoInternaORM).where(
                DestinatarioNotificacaoInternaORM.tenant_id
                == contexto.tenant_id,
                DestinatarioNotificacaoInternaORM.unidade_id
                == contexto.unidade_id,
                DestinatarioNotificacaoInternaORM.canal == canal.value,
                DestinatarioNotificacaoInternaORM.contato_fingerprint
                == fingerprint,
                DestinatarioNotificacaoInternaORM.destinatario_id
                != identificador,
            )
        )
        if conflito is not None:
            raise ValueError("contato interno duplicado no mesmo escopo")

        row = self._session.get(
            DestinatarioNotificacaoInternaORM,
            identificador,
        )
        agora = datetime.now(timezone.utc)
        ciphertext = self._fernet.encrypt(
            normalizado.encode("utf-8")
        ).decode("ascii")
        if row is None:
            row = DestinatarioNotificacaoInternaORM(
                destinatario_id=identificador,
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                nome_exibicao=nome,
                cargo=(cargo or "").strip() or None,
                canal=canal.value,
                referencia_contato=f"internal-contact://{uuid4().hex}",
                contato_fingerprint=fingerprint,
                contato_ciphertext=ciphertext,
                contato_mascara=_mascara_whatsapp(normalizado),
                receber_alertas_estoque=bool(receber_alertas_estoque),
                ativo=bool(ativo),
                versao=1,
                criado_por=contexto.usuario_id,
                atualizado_por=contexto.usuario_id,
                correlation_id=contexto.correlation_id,
                criado_em=agora,
                atualizado_em=agora,
            )
            self._session.add(row)
        else:
            if (
                row.tenant_id != contexto.tenant_id
                or row.unidade_id != contexto.unidade_id
            ):
                raise PermissionError("destinatario fora do escopo ativo")
            row.nome_exibicao = nome
            row.cargo = (cargo or "").strip() or None
            row.canal = canal.value
            row.contato_fingerprint = fingerprint
            row.contato_ciphertext = ciphertext
            row.contato_mascara = _mascara_whatsapp(normalizado)
            row.receber_alertas_estoque = bool(receber_alertas_estoque)
            row.ativo = bool(ativo)
            row.versao += 1
            row.atualizado_por = contexto.usuario_id
            row.correlation_id = contexto.correlation_id
            row.atualizado_em = agora
        self._session.flush()
        return self._dominio(row)

    def atualizar_preferencias(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
        receber_alertas_estoque: bool,
        ativo: bool,
    ) -> DestinatarioNotificacaoInterna:
        row = self._session.get(
            DestinatarioNotificacaoInternaORM,
            destinatario_id,
        )
        if row is None:
            raise LookupError("destinatario interno indisponivel")
        if (
            row.tenant_id != contexto.tenant_id
            or row.unidade_id != contexto.unidade_id
        ):
            raise PermissionError("destinatario fora do escopo ativo")
        row.receber_alertas_estoque = bool(receber_alertas_estoque)
        row.ativo = bool(ativo)
        row.versao += 1
        row.atualizado_por = contexto.usuario_id
        row.correlation_id = contexto.correlation_id
        row.atualizado_em = datetime.now(timezone.utc)
        self._session.flush()
        return self._dominio(row)

    def obter(
        self,
        *,
        contexto: ContextoExecucao,
        destinatario_id: str,
    ) -> DestinatarioNotificacaoInterna | None:
        row = self._session.scalar(
            select(DestinatarioNotificacaoInternaORM).where(
                DestinatarioNotificacaoInternaORM.destinatario_id
                == destinatario_id,
                DestinatarioNotificacaoInternaORM.tenant_id
                == contexto.tenant_id,
                DestinatarioNotificacaoInternaORM.unidade_id
                == contexto.unidade_id,
            )
        )
        return self._dominio(row) if row is not None else None

    def listar_alertas_estoque(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> tuple[DestinatarioNotificacaoInterna, ...]:
        rows = self._session.scalars(
            select(DestinatarioNotificacaoInternaORM)
            .where(
                DestinatarioNotificacaoInternaORM.tenant_id
                == contexto.tenant_id,
                DestinatarioNotificacaoInternaORM.unidade_id
                == contexto.unidade_id,
                DestinatarioNotificacaoInternaORM.ativo.is_(True),
                DestinatarioNotificacaoInternaORM.receber_alertas_estoque.is_(
                    True
                ),
            )
            .order_by(
                DestinatarioNotificacaoInternaORM.nome_exibicao,
                DestinatarioNotificacaoInternaORM.destinatario_id,
            )
        ).all()
        return tuple(self._dominio(row) for row in rows)

    def resolver_contato(
        self,
        *,
        contexto: ContextoExecucao,
        referencia_contato: str,
    ) -> SecretValue:
        referencia = referencia_contato.strip()
        if not referencia.startswith("internal-contact://"):
            raise LookupError("referencia de contato interno invalida")
        row = self._session.scalar(
            select(DestinatarioNotificacaoInternaORM).where(
                DestinatarioNotificacaoInternaORM.referencia_contato
                == referencia,
                DestinatarioNotificacaoInternaORM.tenant_id
                == contexto.tenant_id,
                DestinatarioNotificacaoInternaORM.unidade_id
                == contexto.unidade_id,
            )
        )
        if row is None:
            raise LookupError("contato interno indisponivel no escopo")
        try:
            valor = self._fernet.decrypt(
                row.contato_ciphertext.encode("ascii")
            ).decode("utf-8")
        except (
            InvalidToken,
            UnicodeDecodeError,
            UnicodeEncodeError,
        ) as exc:
            raise LookupError("contato interno nao pode ser resolvido") from exc
        return SecretValue(valor)
