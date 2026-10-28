"""Safe composition of the public NFC-e issuance building blocks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from kordena_fiscal.documents import CanonicalFiscalDocument
from kordena_fiscal.domain import (
    ElectronicInvoiceModel,
    FiscalDocumentKind,
    FiscalDomainError,
    FiscalValidationError,
)
from kordena_fiscal.gateway import (
    AuthorizationRequest,
    AuthorizationResult,
    AuthorizationStatus,
    FiscalGatewayClient,
)
from kordena_fiscal.lifecycle import (
    FiscalDocumentState,
    FiscalStateMachine,
    FiscalStateSnapshot,
    IdempotencyCoordinator,
    IssuanceAttempt,
    IssuanceAttemptStatus,
)
from kordena_fiscal.numbering import FiscalNumberReservation, FiscalSequenceManager
from kordena_fiscal.security import (
    CertificateReference,
    FiscalSigningService,
    SignatureEnvelope,
    SigningRequest,
)
from kordena_fiscal.xml import (
    AccessKeyInput,
    NfceXmlPayload,
    NfeAccessKey,
    XmlValidationResult,
    build_access_key,
)


class NfceIssuanceContractError(FiscalDomainError):
    """Raised when an injected NFC-e adapter violates the orchestration contract."""


class NfceNumericCodeProvider(Protocol):
    """Produce cNF without forcing a randomness policy into the generic Core."""

    def code_for(
        self,
        document: CanonicalFiscalDocument,
        attempt: IssuanceAttempt,
        number: FiscalNumberReservation,
    ) -> int: ...


class NfceXmlBuilder(Protocol):
    """Map the canonical document to one NFC-e XML payload for a fixed access key."""

    def build(
        self,
        document: CanonicalFiscalDocument,
        access_key: NfeAccessKey,
    ) -> NfceXmlPayload: ...


class NfceXmlValidator(Protocol):
    """Validate an NFC-e payload against the approved schema bundle."""

    def validate(self, payload: NfceXmlPayload) -> XmlValidationResult: ...


class NfceSignedXmlAssembler(Protocol):
    """Embed a verified signature envelope into the XML transport artifact."""

    def assemble(
        self,
        payload: NfceXmlPayload,
        signature: SignatureEnvelope,
    ) -> bytes: ...


@dataclass(frozen=True, slots=True)
class NfceIssuanceCommand:
    """Explicit configuration needed to issue one canonical NFC-e."""

    document: CanonicalFiscalDocument
    series: int
    certificate: CertificateReference
    signing_algorithm: str
    emission_type: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.document, CanonicalFiscalDocument):
            raise FiscalValidationError("document must be CanonicalFiscalDocument")
        if self.document.document_kind is not FiscalDocumentKind.NFCE:
            raise FiscalValidationError("NFC-e orchestrator accepts only NFCE documents")
        if not isinstance(self.series, int) or isinstance(self.series, bool):
            raise FiscalValidationError("series must be an integer")
        if self.series < 0 or self.series > 999:
            raise FiscalValidationError("series must be between 0 and 999")
        if not isinstance(self.emission_type, int) or isinstance(self.emission_type, bool):
            raise FiscalValidationError("emission_type must be an integer")
        if self.emission_type < 1 or self.emission_type > 9:
            raise FiscalValidationError("emission_type must be between 1 and 9")
        if not isinstance(self.certificate, CertificateReference):
            raise FiscalValidationError("certificate must be CertificateReference")
        algorithm = self.signing_algorithm.strip()
        if not algorithm:
            raise FiscalValidationError("signing_algorithm must not be blank")
        if len(algorithm) > 256:
            raise FiscalValidationError("signing_algorithm exceeds max length 256")
        object.__setattr__(self, "signing_algorithm", algorithm)
        self.certificate.assert_usable(self.document.scope, self.document.issued_at)


@dataclass(frozen=True, slots=True)
class NfceIssuanceResult:
    """Outcome without retaining private key material or raw signed XML."""

    attempt: IssuanceAttempt
    replay: bool
    number_reservation: FiscalNumberReservation | None = None
    access_key: NfeAccessKey | None = None
    xml_validation: XmlValidationResult | None = None
    signature: SignatureEnvelope | None = None
    signed_xml_sha256: str | None = None
    authorization: AuthorizationResult | None = None
    lifecycle: FiscalStateSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attempt, IssuanceAttempt):
            raise FiscalValidationError("attempt must be IssuanceAttempt")
        if not isinstance(self.replay, bool):
            raise FiscalValidationError("replay must be bool")
        fresh_artifacts = (
            self.number_reservation,
            self.access_key,
            self.xml_validation,
            self.signature,
            self.signed_xml_sha256,
            self.authorization,
            self.lifecycle,
        )
        if self.replay:
            if any(value is not None for value in fresh_artifacts):
                raise FiscalValidationError("replay result cannot expose new issuance artifacts")
            return
        if any(value is None for value in fresh_artifacts):
            raise FiscalValidationError(
                "fresh issuance result requires all orchestration artifacts"
            )
        assert self.authorization is not None
        assert self.lifecycle is not None
        if self.authorization.status is AuthorizationStatus.AUTHORIZED:
            if self.attempt.status is not IssuanceAttemptStatus.AUTHORIZED:
                raise FiscalValidationError("authorized gateway result must authorize the attempt")
            if self.lifecycle.state is not FiscalDocumentState.AUTHORIZED:
                raise FiscalValidationError("authorized gateway result must end AUTHORIZED")
        elif self.authorization.status is AuthorizationStatus.REJECTED:
            if self.attempt.status is not IssuanceAttemptStatus.REJECTED:
                raise FiscalValidationError("rejected gateway result must reject the attempt")
            if self.lifecycle.state is not FiscalDocumentState.REJECTED:
                raise FiscalValidationError("rejected gateway result must end REJECTED")
        else:
            if self.attempt.status is not IssuanceAttemptStatus.RESERVED:
                raise FiscalValidationError("pending gateway result must keep attempt RESERVED")
            if self.lifecycle.state is not FiscalDocumentState.TRANSMITTING:
                raise FiscalValidationError("pending gateway result must remain TRANSMITTING")


class NfceIssuanceOrchestrator:
    """Compose idempotency, numbering, XML, signing, gateway and lifecycle safely."""

    def __init__(
        self,
        *,
        idempotency: IdempotencyCoordinator,
        numbering: FiscalSequenceManager,
        numeric_code_provider: NfceNumericCodeProvider,
        xml_builder: NfceXmlBuilder,
        xml_validator: NfceXmlValidator,
        signing: FiscalSigningService,
        signed_xml_assembler: NfceSignedXmlAssembler,
        gateway: FiscalGatewayClient,
        state_machine: FiscalStateMachine | None = None,
    ) -> None:
        self._idempotency = idempotency
        self._numbering = numbering
        self._numeric_code_provider = numeric_code_provider
        self._xml_builder = xml_builder
        self._xml_validator = xml_validator
        self._signing = signing
        self._signed_xml_assembler = signed_xml_assembler
        self._gateway = gateway
        self._state_machine = state_machine or FiscalStateMachine()

    def issue(self, command: NfceIssuanceCommand) -> NfceIssuanceResult:
        if not isinstance(command, NfceIssuanceCommand):
            raise FiscalValidationError("command must be NfceIssuanceCommand")
        document = command.document
        idempotency_reservation = self._idempotency.begin(document)
        if idempotency_reservation.replay:
            return NfceIssuanceResult(
                attempt=idempotency_reservation.attempt,
                replay=True,
            )

        attempt = idempotency_reservation.attempt
        lifecycle = FiscalStateSnapshot.initial(document.document_id, document.issued_at)
        lifecycle = self._transition(
            lifecycle,
            FiscalDocumentState.VALIDATING,
            document,
            "NFC-e issuance validation started",
        )

        number = self._numbering.reserve(
            document.scope,
            model=ElectronicInvoiceModel.NFCE,
            series=command.series,
        )
        numeric_code = self._numeric_code_provider.code_for(document, attempt, number)
        if not isinstance(numeric_code, int) or isinstance(numeric_code, bool):
            raise NfceIssuanceContractError("numeric-code provider must return an integer")

        municipality_code = document.issuer.address.jurisdiction.municipality_ibge_code
        if municipality_code is None:
            raise NfceIssuanceContractError("issuer municipality IBGE code is required")
        access_key = build_access_key(
            AccessKeyInput(
                state_ibge_code=municipality_code[:2],
                issued_at=document.issued_at,
                issuer_cnpj=document.issuer.cnpj,
                model=ElectronicInvoiceModel.NFCE,
                series=command.series,
                invoice_number=number.number,
                emission_type=command.emission_type,
                numeric_code=numeric_code,
            )
        )

        payload = self._xml_builder.build(document, access_key)
        if not isinstance(payload, NfceXmlPayload):
            raise NfceIssuanceContractError("XML builder must return NfceXmlPayload")
        if payload.access_key != access_key:
            raise NfceIssuanceContractError("XML builder returned a different access key")
        validation = self._xml_validator.validate(payload)
        if not isinstance(validation, XmlValidationResult):
            raise NfceIssuanceContractError("XML validator must return XmlValidationResult")
        expected_xml_digest = hashlib.sha256(payload.xml).hexdigest()
        if validation.xml_sha256 != expected_xml_digest:
            raise NfceIssuanceContractError("XML validator returned a mismatched XML digest")

        lifecycle = self._transition(
            lifecycle,
            FiscalDocumentState.READY_TO_SIGN,
            document,
            "NFC-e XML validated",
        )
        lifecycle = self._transition(
            lifecycle,
            FiscalDocumentState.SIGNING,
            document,
            "NFC-e XML signing started",
        )
        signature = self._signing.sign(
            SigningRequest(
                scope=document.scope,
                certificate=command.certificate,
                payload=payload.xml,
                algorithm=command.signing_algorithm,
                signing_time=document.issued_at,
                purpose="nfce_xml",
            )
        )
        signed_xml = self._signed_xml_assembler.assemble(payload, signature)
        if not isinstance(signed_xml, bytes) or not signed_xml:
            raise NfceIssuanceContractError("signed XML assembler must return non-empty bytes")
        if signed_xml == payload.xml:
            raise NfceIssuanceContractError("signed XML assembler returned the unsigned payload")
        NfceXmlPayload(access_key=access_key, xml=signed_xml)
        signed_xml_sha256 = hashlib.sha256(signed_xml).hexdigest()

        lifecycle = self._transition(
            lifecycle,
            FiscalDocumentState.READY_TO_TRANSMIT,
            document,
            "signed NFC-e transport artifact prepared",
        )
        lifecycle = self._transition(
            lifecycle,
            FiscalDocumentState.TRANSMITTING,
            document,
            "NFC-e authorization requested",
        )
        authorization = self._gateway.authorize(
            AuthorizationRequest(
                scope=document.scope,
                access_key=access_key,
                signed_xml=signed_xml,
                idempotency_key=attempt.key,
                request_fingerprint=attempt.request_fingerprint,
            )
        )

        if authorization.status is AuthorizationStatus.AUTHORIZED:
            protocol_reference = authorization.protocol_reference
            if protocol_reference is None:
                raise NfceIssuanceContractError("authorized result is missing protocol reference")
            lifecycle = self._transition(
                lifecycle,
                FiscalDocumentState.AUTHORIZED,
                document,
                "NFC-e authorization confirmed",
            )
            attempt = self._idempotency.mark_authorized(
                attempt.key,
                attempt.generation,
                protocol_reference,
            )
        elif authorization.status is AuthorizationStatus.REJECTED:
            rejection_code = authorization.rejection_code
            rejection_message = authorization.rejection_message
            if rejection_code is None or rejection_message is None:
                raise NfceIssuanceContractError("rejected result is missing rejection metadata")
            rejection_reason = f"{rejection_code}: {rejection_message}"
            lifecycle = self._transition(
                lifecycle,
                FiscalDocumentState.REJECTED,
                document,
                rejection_reason,
            )
            attempt = self._idempotency.mark_rejected(
                attempt.key,
                attempt.generation,
                rejection_reason,
            )

        return NfceIssuanceResult(
            attempt=attempt,
            replay=False,
            number_reservation=number,
            access_key=access_key,
            xml_validation=validation,
            signature=signature,
            signed_xml_sha256=signed_xml_sha256,
            authorization=authorization,
            lifecycle=lifecycle,
        )

    def _transition(
        self,
        snapshot: FiscalStateSnapshot,
        target: FiscalDocumentState,
        document: CanonicalFiscalDocument,
        reason: str,
    ) -> FiscalStateSnapshot:
        return self._state_machine.transition(
            snapshot,
            target,
            occurred_at=document.issued_at,
            reason=reason,
            correlation_id=document.scope.correlation_id,
        )
