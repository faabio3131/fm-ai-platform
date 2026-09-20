"""Governed signer/gateway adapters for Kordena Fiscal V1 (WP-031I).

This module bridges the frozen provider-neutral Fiscal V1 contracts to Kordena's
existing integration Control Plane and Secret Store. Raw secrets never cross this
infra boundary.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.integracoes.modelos import AmbienteIntegracao
from core.seguranca.segredos import SecretStore, SecretValue
from infra.integracoes.modelos_orm import ServicoExternoConfigORM
from infra.seguranca.modelos_orm import CredencialReferenciaORM
from kordena_fiscal.domain import ExecutionScope, FiscalEnvironment
from kordena_fiscal.gateway import (
    AuthorizationRequest,
    AuthorizationResult,
    FiscalGateway,
)
from kordena_fiscal.operations import (
    CancellationRequest,
    CancellationResult,
    FiscalOperationsGateway,
    FiscalQueryRequest,
    FiscalQueryResult,
    InutilizationRequest,
    InutilizationResult,
)
from kordena_fiscal.security import (
    CertificateReference,
    FiscalSigner,
    FiscalSignerKind,
    SignatureEnvelope,
    SigningRequest,
)

_FISCAL_SERVICE = "fiscal.documentos"
_DEFAULT_PROVIDER = "sefaz"


class FiscalRuntimeConfigurationError(RuntimeError):
    """Fail-closed configuration/readiness error for the fiscal runtime."""


class FiscalProviderUnavailableError(RuntimeError):
    """External fiscal provider/transport is unavailable."""


class FiscalProviderTimeoutError(RuntimeError):
    """External fiscal provider/transport exhausted timeout retries."""


@dataclass(frozen=True, slots=True)
class FiscalRuntimeConfiguration:
    configuracao_id: str
    provider: str
    environment: FiscalEnvironment
    public_parameters: Mapping[str, object]
    credential_purposes: Mapping[str, str]
    homologated: bool
    homologation_evidence_reference: str | None


@dataclass(frozen=True, slots=True)
class ResolvedFiscalCredential:
    role: str
    reference: str
    value: SecretValue


class FiscalProviderTransport(Protocol):
    """Provider-specific private transport used by the governed gateway adapter."""

    def authorize(
        self,
        request: AuthorizationRequest,
        *,
        configuration: FiscalRuntimeConfiguration,
        credentials: Mapping[str, SecretValue],
    ) -> AuthorizationResult: ...

    def query(
        self,
        request: FiscalQueryRequest,
        *,
        configuration: FiscalRuntimeConfiguration,
        credentials: Mapping[str, SecretValue],
    ) -> FiscalQueryResult: ...

    def cancel(
        self,
        request: CancellationRequest,
        *,
        configuration: FiscalRuntimeConfiguration,
        credentials: Mapping[str, SecretValue],
    ) -> CancellationResult: ...

    def inutilize(
        self,
        request: InutilizationRequest,
        *,
        configuration: FiscalRuntimeConfiguration,
        credentials: Mapping[str, SecretValue],
    ) -> InutilizationResult: ...


def _fiscal_environment(value: AmbienteIntegracao) -> FiscalEnvironment:
    if value is AmbienteIntegracao.PRODUCAO:
        return FiscalEnvironment.PRODUCTION
    return FiscalEnvironment.HOMOLOGATION


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalRuntimeConfigurationError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class FiscalControlPlaneResolver:
    """Read-only resolver over the canonical integration Control Plane and vault."""

    def __init__(self, session: Session, secret_store: SecretStore) -> None:
        self._session = session
        self._secret_store = secret_store

    def resolve_environment(self, *, tenant_id: str, unit_id: str) -> FiscalEnvironment:
        rows = self._enabled_configs(tenant_id=tenant_id, unit_id=unit_id)
        if not rows:
            return FiscalEnvironment.HOMOLOGATION
        if len(rows) != 1:
            raise FiscalRuntimeConfigurationError(
                "multiple enabled fiscal configurations for tenant/unit"
            )
        row = rows[0]
        environment = _fiscal_environment(AmbienteIntegracao(row.ambiente))
        if environment is FiscalEnvironment.PRODUCTION:
            self._assert_production_approved(row)
        return environment

    def configuration_for_scope(
        self,
        scope: ExecutionScope,
    ) -> FiscalRuntimeConfiguration:
        rows = self._enabled_configs(
            tenant_id=scope.tenant_id,
            unit_id=scope.unit_id,
        )
        matching = [
            row
            for row in rows
            if _fiscal_environment(AmbienteIntegracao(row.ambiente))
            is scope.environment
        ]
        if len(matching) != 1:
            raise FiscalRuntimeConfigurationError(
                "fiscal configuration unavailable for execution scope"
            )
        row = matching[0]
        if scope.environment is FiscalEnvironment.PRODUCTION:
            self._assert_production_approved(row)
        return FiscalRuntimeConfiguration(
            configuracao_id=row.configuracao_id,
            provider=row.provedor,
            environment=scope.environment,
            public_parameters=dict(row.parametros_publicos),
            credential_purposes=dict(row.finalidades_credenciais),
            homologated=row.homologada,
            homologation_evidence_reference=row.evidencia_homologacao_ref,
        )

    def credential(
        self,
        *,
        scope: ExecutionScope,
        role: str,
        required: bool = True,
    ) -> ResolvedFiscalCredential | None:
        configuration = self.configuration_for_scope(scope)
        purpose = configuration.credential_purposes.get(role)
        if not purpose:
            if required:
                raise FiscalRuntimeConfigurationError(
                    f"missing fiscal credential role: {role}"
                )
            return None
        row = self._session.scalar(
            select(CredencialReferenciaORM)
            .where(
                CredencialReferenciaORM.tenant_id == scope.tenant_id,
                CredencialReferenciaORM.unidade_id == scope.unit_id,
                CredencialReferenciaORM.provedor == configuration.provider,
                CredencialReferenciaORM.finalidade == purpose,
                CredencialReferenciaORM.ativa.is_(True),
            )
            .order_by(CredencialReferenciaORM.versao.desc())
            .limit(1)
        )
        if row is None:
            if required:
                raise FiscalRuntimeConfigurationError(
                    f"active fiscal credential unavailable: {role}"
                )
            return None
        return ResolvedFiscalCredential(
            role=role,
            reference=row.referencia,
            value=self._secret_store.resolve(row.referencia),
        )

    def resolve_certificate(
        self,
        *,
        scope: ExecutionScope,
        instant: datetime,
    ) -> CertificateReference:
        _aware(instant, "instant")
        configuration = self.configuration_for_scope(scope)
        pfx = self.credential(scope=scope, role="certificate_pfx")
        password = self.credential(scope=scope, role="certificate_password")
        assert pfx is not None and password is not None
        _private_key, certificate, _chain = _load_pkcs12(
            pfx.value,
            password.value,
        )
        signer_kind_raw = str(
            configuration.public_parameters.get("signer_kind", "a1_pfx")
        )
        try:
            signer_kind = FiscalSignerKind(signer_kind_raw)
        except ValueError as exc:
            raise FiscalRuntimeConfigurationError(
                "unsupported fiscal signer_kind"
            ) from exc
        if signer_kind is not FiscalSignerKind.A1_PFX:
            raise FiscalRuntimeConfigurationError(
                "current Kordena adapter supports only a1_pfx"
            )
        not_before = certificate.not_valid_before_utc
        expires_at = certificate.not_valid_after_utc
        subject = certificate.subject.rfc4514_string() or None
        return CertificateReference(
            tenant_id=scope.tenant_id,
            unit_id=scope.unit_id,
            reference_id=pfx.reference,
            signer_kind=signer_kind,
            not_before=not_before,
            expires_at=expires_at,
            subject_identifier=subject,
        )

    def gateway_credentials(
        self,
        scope: ExecutionScope,
    ) -> dict[str, SecretValue]:
        result: dict[str, SecretValue] = {}
        for role in ("provider_token", "csc", "csc_id"):
            resolved = self.credential(scope=scope, role=role, required=False)
            if resolved is not None:
                result[role] = resolved.value
        return result

    def _enabled_configs(
        self,
        *,
        tenant_id: str,
        unit_id: str,
    ) -> list[ServicoExternoConfigORM]:
        return list(
            self._session.scalars(
                select(ServicoExternoConfigORM)
                .where(
                    ServicoExternoConfigORM.tenant_id == tenant_id,
                    ServicoExternoConfigORM.unidade_id == unit_id,
                    ServicoExternoConfigORM.servico == _FISCAL_SERVICE,
                    ServicoExternoConfigORM.habilitada.is_(True),
                )
                .order_by(ServicoExternoConfigORM.configuracao_id)
            ).all()
        )

    @staticmethod
    def _assert_production_approved(row: ServicoExternoConfigORM) -> None:
        if row.ambiente != AmbienteIntegracao.PRODUCAO.value:
            raise FiscalRuntimeConfigurationError(
                "production requires explicit production configuration"
            )
        if not row.homologada or not (row.evidencia_homologacao_ref or "").strip():
            raise FiscalRuntimeConfigurationError(
                "production fiscal configuration requires homologation evidence"
            )


class ConfiguredFiscalSignerAdapter(FiscalSigner):
    """A1/PFX signer backed by the canonical Secret Store."""

    def __init__(self, resolver: FiscalControlPlaneResolver) -> None:
        self._resolver = resolver

    def sign(self, request: SigningRequest) -> SignatureEnvelope:
        self._resolver.configuration_for_scope(request.scope)
        pfx = self._resolver.credential(
            scope=request.scope,
            role="certificate_pfx",
        )
        password = self._resolver.credential(
            scope=request.scope,
            role="certificate_password",
        )
        assert pfx is not None and password is not None
        if request.certificate.reference_id != pfx.reference:
            raise FiscalRuntimeConfigurationError(
                "signing certificate is not the active certificate reference"
            )
        private_key, certificate, _chain = _load_pkcs12(
            pfx.value,
            password.value,
        )
        _assert_certificate_matches_reference(certificate, request.certificate)
        algorithm = request.algorithm.strip().casefold()
        signature = _sign_payload(private_key, request.payload, algorithm)
        _verify_signature(
            certificate,
            request.payload,
            signature,
            algorithm,
        )
        return SignatureEnvelope(
            certificate_reference_id=request.certificate.reference_id,
            signer_kind=request.certificate.signer_kind,
            algorithm=request.algorithm,
            signature_value=signature,
            payload_sha256=request.payload_sha256,
            signed_at=request.signing_time,
        )


class ConfiguredFiscalGatewayAdapter(FiscalGateway, FiscalOperationsGateway):
    """Governed gateway adapter with bounded retry and private credentials."""

    def __init__(
        self,
        resolver: FiscalControlPlaneResolver,
        transport: FiscalProviderTransport,
        *,
        max_attempts: int = 2,
    ) -> None:
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or max_attempts < 1
            or max_attempts > 5
        ):
            raise ValueError("max_attempts must be an integer between 1 and 5")
        self._resolver = resolver
        self._transport = transport
        self._max_attempts = max_attempts

    def authorize(self, request: AuthorizationRequest) -> AuthorizationResult:
        return self._dispatch("authorize", request)

    def query(self, request: FiscalQueryRequest) -> FiscalQueryResult:
        return self._dispatch("query", request)

    def cancel(self, request: CancellationRequest) -> CancellationResult:
        return self._dispatch("cancel", request)

    def inutilize(self, request: InutilizationRequest) -> InutilizationResult:
        return self._dispatch("inutilize", request)

    def _dispatch(self, operation: str, request):
        configuration = self._resolver.configuration_for_scope(request.scope)
        credentials = self._resolver.gateway_credentials(request.scope)
        for attempt in range(1, self._max_attempts + 1):
            try:
                method = getattr(self._transport, operation)
                return method(
                    request,
                    configuration=configuration,
                    credentials=credentials,
                )
            except TimeoutError as exc:
                if attempt == self._max_attempts:
                    raise FiscalProviderTimeoutError(
                        "fiscal provider timeout"
                    ) from exc
            except ConnectionError as exc:
                if attempt == self._max_attempts:
                    raise FiscalProviderUnavailableError(
                        "fiscal provider unavailable"
                    ) from exc
        raise AssertionError("unreachable")


def _decode_pfx(value: SecretValue) -> bytes:
    raw = value.reveal().strip()
    try:
        return base64.b64decode(raw, validate=True)
    except (ValueError, TypeError) as exc:
        raise FiscalRuntimeConfigurationError(
            "certificate_pfx must be base64 encoded"
        ) from exc


def _load_pkcs12(
    pfx: SecretValue,
    password: SecretValue,
):
    try:
        key, certificate, chain = pkcs12.load_key_and_certificates(
            _decode_pfx(pfx),
            password.reveal().encode("utf-8"),
        )
    except (ValueError, TypeError) as exc:
        raise FiscalRuntimeConfigurationError(
            "unable to load configured fiscal certificate"
        ) from exc
    if key is None or certificate is None:
        raise FiscalRuntimeConfigurationError(
            "configured PFX must contain private key and certificate"
        )
    return key, certificate, chain


def _assert_certificate_matches_reference(
    certificate: x509.Certificate,
    reference: CertificateReference,
) -> None:
    if certificate.not_valid_before_utc != reference.not_before:
        raise FiscalRuntimeConfigurationError(
            "certificate not_before differs from resolved reference"
        )
    if certificate.not_valid_after_utc != reference.expires_at:
        raise FiscalRuntimeConfigurationError(
            "certificate expires_at differs from resolved reference"
        )


def _sign_payload(private_key, payload: bytes, algorithm: str) -> bytes:
    if isinstance(private_key, rsa.RSAPrivateKey):
        if algorithm not in {"rsa-sha256", "sha256"}:
            raise FiscalRuntimeConfigurationError(
                "unsupported RSA fiscal signing algorithm"
            )
        return private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        if algorithm not in {"ecdsa-sha256", "sha256"}:
            raise FiscalRuntimeConfigurationError(
                "unsupported ECDSA fiscal signing algorithm"
            )
        return private_key.sign(payload, ec.ECDSA(hashes.SHA256()))
    raise FiscalRuntimeConfigurationError(
        "unsupported private key type for fiscal signing"
    )


def _verify_signature(
    certificate: x509.Certificate,
    payload: bytes,
    signature: bytes,
    algorithm: str,
) -> None:
    public_key = certificate.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        if algorithm not in {"rsa-sha256", "sha256"}:
            raise FiscalRuntimeConfigurationError(
                "unsupported RSA fiscal signing algorithm"
            )
        public_key.verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        return
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        if algorithm not in {"ecdsa-sha256", "sha256"}:
            raise FiscalRuntimeConfigurationError(
                "unsupported ECDSA fiscal signing algorithm"
            )
        public_key.verify(signature, payload, ec.ECDSA(hashes.SHA256()))
        return
    raise FiscalRuntimeConfigurationError(
        "unsupported public key type for fiscal signature verification"
    )


__all__ = [
    "ConfiguredFiscalGatewayAdapter",
    "ConfiguredFiscalSignerAdapter",
    "FiscalControlPlaneResolver",
    "FiscalEnvironmentResolver",
    "FiscalProviderTimeoutError",
    "FiscalProviderTransport",
    "FiscalProviderUnavailableError",
    "FiscalRuntimeConfiguration",
    "FiscalRuntimeConfigurationError",
    "ResolvedFiscalCredential",
]


FiscalEnvironmentResolver = FiscalControlPlaneResolver
