"""Caso de uso de recuperação e redefinição de senha Kordena."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy
from infra.seguranca.modelos_orm import EventoAuditoriaORM
from infra.seguranca.password_recovery_orm import PasswordRecoveryTokenORM

SessionFactory = Callable[[], Session]
_DEFAULT_TTL = timedelta(minutes=30)


class PasswordRecoveryError(ValueError):
    pass


class PasswordRecoveryDispatcher(Protocol):
    def send_password_reset(self, *, email: str, token: str) -> None: ...

    def send_password_changed(self, *, email: str) -> None: ...


@dataclass(frozen=True, kw_only=True)
class PasswordRecoveryRequest:
    email: str
    token: str


@dataclass(frozen=True, kw_only=True)
class PasswordResetResult:
    identity_user_id: str
    membership_id: str
    email: str
    tenant_id: str
    unidade_id: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _normalize_email(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or "@" not in normalized or len(normalized) > 320:
        raise ValueError("email_invalido")
    return normalized


def _audit(
    session: Session,
    *,
    action: str,
    result: str,
    reason: str,
    correlation_id: str,
    identity,
) -> None:
    session.add(
        EventoAuditoriaORM(
            audit_id=str(uuid4()),
            tenant_id=identity.tenant_id,
            unidade_id=identity.unidade_id,
            usuario_id=identity.usuario_id,
            papel_efetivo=(
                min(papel.value for papel in identity.papeis)
                if identity.papeis
                else None
            ),
            acao=action,
            recurso_tipo="identity_user",
            recurso_id=identity.global_identity_id,
            resultado=result,
            motivo=reason,
            correlation_id=correlation_id,
            timestamp=_now(),
            origem="auth.password_recovery",
            politica="password-recovery-v1",
            versao=1,
            causation_id=None,
            antes_resumido={},
            depois_resumido={},
            metadata_segura={},
        )
    )


class AplicacaoPasswordRecoveryV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        ttl: timedelta = _DEFAULT_TTL,
    ) -> None:
        if ttl < timedelta(minutes=5) or ttl > timedelta(hours=2):
            raise ValueError("password_recovery_ttl_invalido")
        self._session_factory = session_factory
        self._ttl = ttl

    def solicitar(
        self,
        *,
        email: str,
        correlation_id: str,
    ) -> PasswordRecoveryRequest | None:
        normalized = _normalize_email(email)
        corr = correlation_id.strip()
        if not corr or len(corr) > 128:
            raise ValueError("correlation_id_invalido")

        now = _now()
        token = secrets.token_urlsafe(48)

        with self._session_factory() as session, session.begin():
            repo = RepositorioIdentidadesSQLAlchemy(session)
            identity = repo.obter_por_email(normalized)
            if identity is None or not identity.ativo:
                return None

            session.execute(
                update(PasswordRecoveryTokenORM)
                .where(
                    PasswordRecoveryTokenORM.identity_user_id
                    == identity.global_identity_id,
                    PasswordRecoveryTokenORM.used_at.is_(None),
                )
                .values(used_at=now)
            )
            session.add(
                PasswordRecoveryTokenORM(
                    request_id=str(uuid4()),
                    identity_user_id=identity.global_identity_id,
                    email=normalized,
                    token_sha256=_token_hash(token),
                    correlation_id=corr,
                    created_at=now,
                    expires_at=now + self._ttl,
                    used_at=None,
                )
            )
            _audit(
                session,
                action="auth.password_recovery.requested",
                result="success",
                reason="password reset requested",
                correlation_id=corr,
                identity=identity,
            )

        return PasswordRecoveryRequest(email=normalized, token=token)

    def redefinir(
        self,
        *,
        token: str,
        nova_senha: str,
        correlation_id: str,
    ) -> PasswordResetResult:
        raw_token = token.strip()
        corr = correlation_id.strip()
        if not raw_token or len(raw_token) > 1024 or not corr or len(corr) > 128:
            raise PasswordRecoveryError("password_recovery_token_invalid")

        now = _now()
        token_sha = _token_hash(raw_token)

        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(PasswordRecoveryTokenORM)
                .where(PasswordRecoveryTokenORM.token_sha256 == token_sha)
                .with_for_update()
            )
            if row is None or row.used_at is not None:
                raise PasswordRecoveryError("password_recovery_token_invalid")

            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                row.used_at = now
                raise PasswordRecoveryError("password_recovery_token_invalid")

            repo = RepositorioIdentidadesSQLAlchemy(session)
            memberships = repo.listar_memberships(
                identity_user_id=row.identity_user_id,
            )
            identity = next((item for item in memberships if item.ativo), None)
            if identity is None:
                row.used_at = now
                raise PasswordRecoveryError("password_recovery_token_invalid")

            try:
                repo.trocar_senha(
                    usuario_id=identity.membership_subject_id,
                    nova_senha=nova_senha,
                )
            except (TypeError, ValueError) as exc:
                raise PasswordRecoveryError("password_recovery_password_invalid") from exc

            row.used_at = now
            session.execute(
                update(PasswordRecoveryTokenORM)
                .where(
                    PasswordRecoveryTokenORM.identity_user_id
                    == row.identity_user_id,
                    PasswordRecoveryTokenORM.request_id != row.request_id,
                    PasswordRecoveryTokenORM.used_at.is_(None),
                )
                .values(used_at=now)
            )
            _audit(
                session,
                action="auth.password_recovery.completed",
                result="success",
                reason="password reset completed",
                correlation_id=corr,
                identity=identity,
            )
            return PasswordResetResult(
                identity_user_id=identity.global_identity_id,
                membership_id=identity.membership_subject_id,
                email=identity.email,
                tenant_id=identity.tenant_id,
                unidade_id=identity.unidade_id,
            )

    def alterar_senha_autenticada(
        self,
        *,
        identity,
        nova_senha: str,
        correlation_id: str,
    ) -> PasswordResetResult:
        corr = correlation_id.strip()
        if not corr or len(corr) > 128:
            raise ValueError("correlation_id_invalido")
        with self._session_factory() as session, session.begin():
            repo = RepositorioIdentidadesSQLAlchemy(session)
            try:
                repo.trocar_senha(
                    usuario_id=identity.membership_subject_id,
                    nova_senha=nova_senha,
                )
            except (TypeError, ValueError) as exc:
                raise PasswordRecoveryError("password_recovery_password_invalid") from exc
            _audit(
                session,
                action="auth.password_changed",
                result="success",
                reason="authenticated password change",
                correlation_id=corr,
                identity=identity,
            )
        return PasswordResetResult(
            identity_user_id=identity.global_identity_id,
            membership_id=identity.membership_subject_id,
            email=identity.email,
            tenant_id=identity.tenant_id,
            unidade_id=identity.unidade_id,
        )
