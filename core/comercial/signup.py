"""Domínio do cadastro público KCA-06."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class EstadoSignup(StrEnum):
    EMAIL_PENDING = "email_pending"
    EMAIL_VERIFIED = "email_verified"
    PROVISIONING_REQUESTED = "provisioning_requested"
    READY = "ready"
    FAILED_RETRYABLE = "failed_retryable"


@dataclass(frozen=True, kw_only=True)
class SignupIntent:
    signup_id: str
    status: EstadoSignup
    owner_name: str
    owner_email: str
    primary_contact_phone: str | None
    establishment_name: str
    segment: str
    terms_accepted: bool
    consent_json: dict[str, bool]
    credential_ciphertext: str | None
    verification_token_sha256: str
    verification_expires_at: datetime
    verified_at: datetime | None
    provisioning_id: str | None
    resend_count: int
    last_sent_at: datetime
    last_error: str | None
    correlation_id: str
    created_at: datetime
    updated_at: datetime
    version: int
