"""Secret-free certificate metadata and fiscal signer boundary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from kordena_fiscal.domain import ExecutionScope, FiscalDomainError, FiscalValidationError


class CertificateValidityError(FiscalDomainError):
    """Raised when a certificate reference is not valid for a signing instant/scope."""


class SignerContractError(FiscalDomainError):
    """Raised when a signer adapter violates the public signing contract."""


class FiscalSignerKind(StrEnum):
    """Pluggable signer families; private-key handling remains inside adapters."""

    A1_PFX = "a1_pfx"
    CLOUD_CERTIFICATE = "cloud_certificate"
    HSM = "hsm"
    REMOTE_SIGNATURE = "remote_signature"
    ELECTRONIC_SEAL = "electronic_seal"


class CertificateStatus(StrEnum):
    NOT_YET_VALID = "not_yet_valid"
    VALID = "valid"
    EXPIRING = "expiring"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class CertificateReference:
    """Metadata/reference only; never contains private key or password material."""

    tenant_id: str
    unit_id: str
    reference_id: str
    signer_kind: FiscalSignerKind
    not_before: datetime
    expires_at: datetime
    subject_identifier: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenant_id", _required(self.tenant_id, "tenant_id", 128))
        object.__setattr__(self, "unit_id", _required(self.unit_id, "unit_id", 128))
        object.__setattr__(
            self,
            "reference_id",
            _required(self.reference_id, "reference_id", 256),
        )
        if not isinstance(self.signer_kind, FiscalSignerKind):
            raise FiscalValidationError("signer_kind must be FiscalSignerKind")
        _require_aware(self.not_before, "not_before")
        _require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.not_before:
            raise FiscalValidationError("expires_at must be after not_before")
        if self.subject_identifier is not None:
            subject = self.subject_identifier.strip()
            if len(subject) > 256:
                raise FiscalValidationError("subject_identifier exceeds max length 256")
            object.__setattr__(self, "subject_identifier", subject or None)

    def status_at(
        self,
        instant: datetime,
        *,
        expiring_within: timedelta = timedelta(days=30),
    ) -> CertificateStatus:
        _require_aware(instant, "instant")
        if expiring_within < timedelta(0):
            raise FiscalValidationError("expiring_within must be non-negative")
        if instant < self.not_before:
            return CertificateStatus.NOT_YET_VALID
        if instant >= self.expires_at:
            return CertificateStatus.EXPIRED
        if self.expires_at - instant <= expiring_within:
            return CertificateStatus.EXPIRING
        return CertificateStatus.VALID

    def assert_usable(self, scope: ExecutionScope, instant: datetime) -> None:
        if not isinstance(scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        _require_aware(instant, "instant")
        if (scope.tenant_id, scope.unit_id) != (self.tenant_id, self.unit_id):
            raise CertificateValidityError("certificate reference does not belong to scope")
        status = self.status_at(instant, expiring_within=timedelta(0))
        if status in {CertificateStatus.NOT_YET_VALID, CertificateStatus.EXPIRED}:
            raise CertificateValidityError(f"certificate reference is {status.value}")


@dataclass(frozen=True, slots=True)
class SigningRequest:
    """Secret-free request passed to a signer adapter."""

    scope: ExecutionScope
    certificate: CertificateReference
    payload: bytes
    algorithm: str
    signing_time: datetime
    purpose: str = "fiscal_document"

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be ExecutionScope")
        if not isinstance(self.certificate, CertificateReference):
            raise FiscalValidationError("certificate must be CertificateReference")
        if not isinstance(self.payload, bytes) or not self.payload:
            raise FiscalValidationError("payload must be non-empty bytes")
        object.__setattr__(self, "algorithm", _required(self.algorithm, "algorithm", 256))
        object.__setattr__(self, "purpose", _required(self.purpose, "purpose", 128))
        _require_aware(self.signing_time, "signing_time")

    @property
    def payload_sha256(self) -> str:
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    """Signer result with enough metadata to detect adapter mix-ups/tampering."""

    certificate_reference_id: str
    signer_kind: FiscalSignerKind
    algorithm: str
    signature_value: bytes
    payload_sha256: str
    signed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "certificate_reference_id",
            _required(self.certificate_reference_id, "certificate_reference_id", 256),
        )
        if not isinstance(self.signer_kind, FiscalSignerKind):
            raise FiscalValidationError("signer_kind must be FiscalSignerKind")
        object.__setattr__(self, "algorithm", _required(self.algorithm, "algorithm", 256))
        if not isinstance(self.signature_value, bytes) or not self.signature_value:
            raise FiscalValidationError("signature_value must be non-empty bytes")
        if len(self.payload_sha256) != 64:
            raise FiscalValidationError("payload_sha256 must be SHA-256 hex")
        try:
            int(self.payload_sha256, 16)
        except ValueError as exc:
            raise FiscalValidationError("payload_sha256 must be hexadecimal") from exc
        _require_aware(self.signed_at, "signed_at")


class FiscalSigner(Protocol):
    """Adapter contract. Implementations own key retrieval/use and never expose it."""

    def sign(self, request: SigningRequest) -> SignatureEnvelope: ...


class FiscalSigningService:
    """Validates public invariants before and after delegating to a signer adapter."""

    def __init__(self, signer: FiscalSigner) -> None:
        self._signer = signer

    def sign(self, request: SigningRequest) -> SignatureEnvelope:
        if not isinstance(request, SigningRequest):
            raise FiscalValidationError("request must be SigningRequest")
        request.certificate.assert_usable(request.scope, request.signing_time)
        result = self._signer.sign(request)
        self._validate_result(request, result)
        return result

    @staticmethod
    def _validate_result(request: SigningRequest, result: SignatureEnvelope) -> None:
        if not isinstance(result, SignatureEnvelope):
            raise SignerContractError("signer must return SignatureEnvelope")
        if result.certificate_reference_id != request.certificate.reference_id:
            raise SignerContractError("signer returned a different certificate reference")
        if result.signer_kind is not request.certificate.signer_kind:
            raise SignerContractError("signer returned a different signer kind")
        if result.algorithm != request.algorithm:
            raise SignerContractError("signer returned a different algorithm")
        if result.payload_sha256 != request.payload_sha256:
            raise SignerContractError("signer returned a mismatched payload digest")
        if result.signed_at < request.signing_time:
            raise SignerContractError("signer result predates requested signing time")


def _required(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError(f"{field_name} must be timezone-aware")
