"""Aplicação do cadastro público e verificação KCA-06."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from application.commercial_provisioning import AplicacaoProvisioningKordenaV1
from core.comercial.erros import DadoComercialInvalido, RegistroComercialDuplicado
from core.comercial.signup import EstadoSignup, SignupIntent
from core.seguranca.segredos import SecretStore
from infra.comercial.modelos_orm import CommercialAuditORM
from infra.comercial.signup_orm import FMPublicSignupIntentORM
from infra.comercial.signup_sqlalchemy import RepositorioPublicSignupSQLAlchemy
from infra.seguranca.adaptador_sqlalchemy import RepositorioIdentidadesSQLAlchemy

SessionFactory = Callable[[], Session]
_SIGNUP_SECRET_REFERENCE = "env:FM_AI_SIGNUP_SECRET_KEY"


class SignupVerificationError(DadoComercialInvalido):
    pass


@dataclass(frozen=True, kw_only=True)
class SignupCreationResult:
    signup: SignupIntent
    verification_token: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(value: str) -> str:
    email = value.strip().casefold()
    if not email or "@" not in email or len(email) > 320:
        raise DadoComercialInvalido("signup_email_invalido")
    return email


def _clean(value: str, *, field: str, max_length: int) -> str:
    cleaned = " ".join(value.split())
    if not cleaned or len(cleaned) > max_length:
        raise DadoComercialInvalido(f"signup_{field}_invalido")
    return cleaned


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AplicacaoPublicSignupV1:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        secret_store: SecretStore,
        credential_secret_reference: str = _SIGNUP_SECRET_REFERENCE,
        verification_ttl_seconds: int = 30 * 60,
        resend_cooldown_seconds: int = 60,
        max_resends: int = 5,
        provisioning: AplicacaoProvisioningKordenaV1 | None = None,
    ) -> None:
        if verification_ttl_seconds < 60:
            raise ValueError("verification_ttl_seconds_invalido")
        self._session_factory = session_factory
        self._secret_store = secret_store
        self._secret_reference = credential_secret_reference
        self._verification_ttl = timedelta(seconds=verification_ttl_seconds)
        self._resend_cooldown = timedelta(seconds=resend_cooldown_seconds)
        self._max_resends = max_resends
        self._provisioning = provisioning or AplicacaoProvisioningKordenaV1(
            session_factory
        )

    def _fernet(self) -> Fernet:
        raw = self._secret_store.resolve(self._secret_reference).reveal().strip()
        try:
            return Fernet(raw.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise RuntimeError("signup_credential_key_invalida") from exc

    def _encrypt_password(self, password: str) -> str:
        if len(password) < 8 or len(password) > 1024:
            raise DadoComercialInvalido("signup_password_invalida")
        return self._fernet().encrypt(password.encode("utf-8")).decode("ascii")

    def _decrypt_password(self, ciphertext: str | None) -> str:
        if not ciphertext:
            raise SignupVerificationError("signup_credential_indisponivel")
        try:
            return self._fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError, UnicodeEncodeError) as exc:
            raise SignupVerificationError("signup_credential_indisponivel") from exc

    def criar_intencao(
        self,
        *,
        owner_name: str,
        owner_email: str,
        owner_password: str,
        primary_contact_phone: str | None,
        establishment_name: str,
        segment: str,
        terms_accepted: bool,
        consent_json: dict[str, bool],
        correlation_id: str,
    ) -> SignupCreationResult:
        email = _normalize_email(owner_email)
        if not terms_accepted:
            raise DadoComercialInvalido("signup_terms_required")
        name = _clean(owner_name, field="owner_name", max_length=255)
        establishment = _clean(
            establishment_name, field="establishment_name", max_length=255
        )
        segment_clean = _clean(segment, field="segment", max_length=96)
        corr = correlation_id.strip()
        if not corr or len(corr) > 128:
            raise DadoComercialInvalido("signup_correlation_invalido")
        phone = (
            " ".join(primary_contact_phone.split())
            if primary_contact_phone and primary_contact_phone.strip()
            else None
        )
        now = _now()
        token = secrets.token_urlsafe(32)
        ciphertext = self._encrypt_password(owner_password)

        try:
            with self._session_factory() as session, session.begin():
                identities = RepositorioIdentidadesSQLAlchemy(session)
                existing_membership = identities.obter_por_email(email)
                repo = RepositorioPublicSignupSQLAlchemy(session)
                pending = repo.obter_pendente_por_email(email)
                if existing_membership is not None or pending is not None:
                    raise RegistroComercialDuplicado("signup_indisponivel")
                signup = repo.adicionar(
                    FMPublicSignupIntentORM(
                        signup_id=str(uuid4()),
                        status=EstadoSignup.EMAIL_PENDING.value,
                        owner_name=name,
                        owner_email=email,
                        primary_contact_phone=phone,
                        establishment_name=establishment,
                        segment=segment_clean,
                        terms_accepted=True,
                        consent_json=dict(consent_json),
                        credential_ciphertext=ciphertext,
                        verification_token_sha256=_token_hash(token),
                        verification_expires_at=now + self._verification_ttl,
                        verified_at=None,
                        provisioning_id=None,
                        resend_count=0,
                        last_sent_at=now,
                        last_error=None,
                        correlation_id=corr,
                        created_at=now,
                        updated_at=now,
                        version=1,
                    )
                )
                session.add(
                    CommercialAuditORM(
                        audit_id=str(uuid4()),
                        actor_user_id="public-signup-v1",
                        action="commercial.signup.created",
                        aggregate_type="public_signup",
                        aggregate_id=signup.signup_id,
                        result="success",
                        reason="KCA-06 public signup intent",
                        correlation_id=signup.correlation_id,
                        causation_id=None,
                        metadata_safe={"status": signup.status.value},
                        timestamp=now,
                    )
                )
        except IntegrityError as exc:
            raise RegistroComercialDuplicado("signup_indisponivel") from exc
        return SignupCreationResult(signup=signup, verification_token=token)

    def obter_status(self, *, signup_id: str) -> SignupIntent | None:
        with self._session_factory() as session:
            return RepositorioPublicSignupSQLAlchemy(session).obter(signup_id.strip())

    def reenviar_token(self, *, signup_id: str) -> SignupCreationResult:
        now = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioPublicSignupSQLAlchemy(session)
            signup = repo.obter(signup_id.strip())
            if signup is None:
                raise SignupVerificationError("signup_not_found")
            if signup.status != EstadoSignup.EMAIL_PENDING:
                raise SignupVerificationError("signup_verification_not_pending")
            if signup.resend_count >= self._max_resends:
                raise SignupVerificationError("signup_resend_limit")
            if now < signup.last_sent_at + self._resend_cooldown:
                raise SignupVerificationError("signup_resend_cooldown")
            token = secrets.token_urlsafe(32)
            updated = repo.atualizar(
                signup_id=signup.signup_id,
                expected_version=signup.version,
                values={
                    "verification_token_sha256": _token_hash(token),
                    "verification_expires_at": now + self._verification_ttl,
                    "resend_count": signup.resend_count + 1,
                    "last_sent_at": now,
                },
            )
        return SignupCreationResult(signup=updated, verification_token=token)

    def verificar_e_provisionar(
        self,
        *,
        signup_id: str,
        verification_token: str,
    ) -> SignupIntent:
        now = _now()
        with self._session_factory() as session, session.begin():
            repo = RepositorioPublicSignupSQLAlchemy(session)
            signup = repo.obter(signup_id.strip())
            if signup is None:
                raise SignupVerificationError("signup_verification_invalid")
            if signup.status != EstadoSignup.EMAIL_PENDING:
                raise SignupVerificationError("signup_verification_already_used")
            if now >= signup.verification_expires_at:
                raise SignupVerificationError("signup_verification_expired")
            supplied = _token_hash(verification_token.strip())
            if not hmac.compare_digest(signup.verification_token_sha256, supplied):
                raise SignupVerificationError("signup_verification_invalid")
            signup = repo.atualizar(
                signup_id=signup.signup_id,
                expected_version=signup.version,
                values={
                    "status": EstadoSignup.EMAIL_VERIFIED.value,
                    "verified_at": now,
                    "verification_token_sha256": _token_hash(
                        secrets.token_urlsafe(32)
                    ),
                },
            )
            session.add(
                CommercialAuditORM(
                    audit_id=str(uuid4()),
                    actor_user_id="public-signup-v1",
                    action="commercial.signup.email_verified",
                    aggregate_type="public_signup",
                    aggregate_id=signup.signup_id,
                    result="success",
                    reason="KCA-06 email verification",
                    correlation_id=signup.correlation_id,
                    causation_id=None,
                    metadata_safe={"status": signup.status.value},
                    timestamp=now,
                )
            )

        password = self._decrypt_password(signup.credential_ciphertext)
        try:
            provisioning = self._provisioning.solicitar(
                idempotency_key=f"signup:{signup.signup_id}",
                owner_email=signup.owner_email,
                owner_password=password,
                display_name=signup.establishment_name,
                primary_contact_phone=signup.primary_contact_phone,
                correlation_id=signup.correlation_id,
            )
            with self._session_factory() as session, session.begin():
                repo = RepositorioPublicSignupSQLAlchemy(session)
                current = repo.obter(signup.signup_id)
                if current is None:
                    raise SignupVerificationError("signup_not_found")
                current = repo.atualizar(
                    signup_id=current.signup_id,
                    expected_version=current.version,
                    values={
                        "status": EstadoSignup.PROVISIONING_REQUESTED.value,
                        "provisioning_id": provisioning.provisioning_id,
                    },
                )
            ready = self._provisioning.executar(
                provisioning_id=provisioning.provisioning_id,
                owner_password=password,
            )
        except (ValueError, RuntimeError, SQLAlchemyError) as exc:
            with self._session_factory() as session, session.begin():
                repo = RepositorioPublicSignupSQLAlchemy(session)
                current = repo.obter(signup.signup_id)
                if current is not None and current.status != EstadoSignup.READY:
                    repo.atualizar(
                        signup_id=current.signup_id,
                        expected_version=current.version,
                        values={
                            "status": EstadoSignup.FAILED_RETRYABLE.value,
                            "last_error": f"{type(exc).__name__}:{str(exc)[:300]}",
                        },
                    )
                    session.add(
                        CommercialAuditORM(
                            audit_id=str(uuid4()),
                            actor_user_id="public-signup-v1",
                            action="commercial.signup.provisioning_failed",
                            aggregate_type="public_signup",
                            aggregate_id=current.signup_id,
                            result="failure",
                            reason="KCA-06 provisioning retryable failure",
                            correlation_id=current.correlation_id,
                            causation_id=current.provisioning_id,
                            metadata_safe={"status": EstadoSignup.FAILED_RETRYABLE.value},
                            timestamp=_now(),
                        )
                    )
            raise

        with self._session_factory() as session, session.begin():
            repo = RepositorioPublicSignupSQLAlchemy(session)
            current = repo.obter(signup.signup_id)
            if current is None:
                raise SignupVerificationError("signup_not_found")
            completed = repo.atualizar(
                signup_id=current.signup_id,
                expected_version=current.version,
                values={
                    "status": EstadoSignup.READY.value,
                    "provisioning_id": ready.provisioning_id,
                    "credential_ciphertext": None,
                    "last_error": None,
                },
            )
            session.add(
                CommercialAuditORM(
                    audit_id=str(uuid4()),
                    actor_user_id="public-signup-v1",
                    action="commercial.signup.ready",
                    aggregate_type="public_signup",
                    aggregate_id=completed.signup_id,
                    result="success",
                    reason="KCA-06 signup provisioning completed",
                    correlation_id=completed.correlation_id,
                    causation_id=ready.provisioning_id,
                    metadata_safe={"status": completed.status.value},
                    timestamp=_now(),
                )
            )
            return completed
