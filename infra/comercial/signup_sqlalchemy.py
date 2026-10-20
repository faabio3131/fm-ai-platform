"""Repositório SQLAlchemy do cadastro público KCA-06."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from core.comercial.signup import EstadoSignup, SignupIntent
from infra.comercial.signup_orm import FMPublicSignupIntentORM


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _model(row: FMPublicSignupIntentORM) -> SignupIntent:
    return SignupIntent(
        signup_id=row.signup_id,
        status=EstadoSignup(row.status),
        owner_name=row.owner_name,
        owner_email=row.owner_email,
        primary_contact_phone=row.primary_contact_phone,
        establishment_name=row.establishment_name,
        segment=row.segment,
        terms_accepted=row.terms_accepted,
        consent_json=dict(row.consent_json or {}),
        credential_ciphertext=row.credential_ciphertext,
        verification_token_sha256=row.verification_token_sha256,
        verification_expires_at=_utc(row.verification_expires_at),
        verified_at=_utc(row.verified_at) if row.verified_at else None,
        provisioning_id=row.provisioning_id,
        resend_count=row.resend_count,
        last_sent_at=_utc(row.last_sent_at),
        last_error=row.last_error,
        correlation_id=row.correlation_id,
        created_at=_utc(row.created_at),
        updated_at=_utc(row.updated_at),
        version=row.version,
    )


class RepositorioPublicSignupSQLAlchemy:
    def __init__(self, session: Session) -> None:
        self._session = session

    def obter(self, signup_id: str) -> SignupIntent | None:
        row = self._session.get(FMPublicSignupIntentORM, signup_id)
        return _model(row) if row is not None else None

    def obter_pendente_por_email(self, email: str) -> SignupIntent | None:
        row = self._session.scalar(
            select(FMPublicSignupIntentORM)
            .where(
                FMPublicSignupIntentORM.owner_email == email,
                FMPublicSignupIntentORM.status.in_(
                    (
                        EstadoSignup.EMAIL_PENDING.value,
                        EstadoSignup.EMAIL_VERIFIED.value,
                        EstadoSignup.PROVISIONING_REQUESTED.value,
                        EstadoSignup.FAILED_RETRYABLE.value,
                    )
                ),
            )
            .order_by(FMPublicSignupIntentORM.created_at.desc())
        )
        return _model(row) if row is not None else None

    def adicionar(self, row: FMPublicSignupIntentORM) -> SignupIntent:
        self._session.add(row)
        self._session.flush()
        return _model(row)

    def atualizar(
        self,
        *,
        signup_id: str,
        expected_version: int,
        values: dict[str, object],
    ) -> SignupIntent:
        payload = dict(values)
        payload["version"] = expected_version + 1
        payload["updated_at"] = datetime.now(timezone.utc)
        result = self._session.execute(
            update(FMPublicSignupIntentORM)
            .where(
                FMPublicSignupIntentORM.signup_id == signup_id,
                FMPublicSignupIntentORM.version == expected_version,
            )
            .values(**payload)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise RuntimeError("signup_concurrency_conflict")
        self._session.flush()
        current = self.obter(signup_id)
        if current is None:
            raise RuntimeError("signup_missing_after_update")
        return current
