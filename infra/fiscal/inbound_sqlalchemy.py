"""Durable inbound fiscal repository with atomic DF-e checkpointing."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from infra.fiscal.modelos_orm import (
    FiscalDfeCheckpointORM,
    FiscalInboundDocumentORM,
    FiscalInboundItemORM,
    FiscalManifestationORM,
)
from kordena_fiscal.domain import (
    Cnpj,
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from kordena_fiscal.inbound import (
    FiscalInboundDocument,
    FiscalInboundSource,
    FiscalInboundStatus,
    FiscalManifestation,
    FiscalNsuCheckpoint,
    parse_nfe_xml,
)
from kordena_fiscal.inbound.models import normalize_nsu

SessionFactory = Callable[[], Session]


class FiscalInboundStoreError(RuntimeError):
    """Base durable inbound persistence error."""


class FiscalInboundConflictError(FiscalInboundStoreError):
    """An inbound identity was replayed with different content."""


class FiscalCheckpointConflictError(FiscalInboundStoreError):
    """The requested checkpoint would regress or cross a partition."""


class FiscalInboundNotFoundError(FiscalInboundStoreError):
    """The requested inbound document does not exist in this partition."""


def _db_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc)


class FiscalInboundStoreSQLAlchemy:
    """One authority for Inbox, DF-e checkpoint and manifestation persistence."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    @staticmethod
    def _document_query(scope: ExecutionScope, access_key: str):
        return select(FiscalInboundDocumentORM).where(
            FiscalInboundDocumentORM.tenant_id == scope.tenant_id,
            FiscalInboundDocumentORM.unit_id == scope.unit_id,
            FiscalInboundDocumentORM.environment == scope.environment.value,
            FiscalInboundDocumentORM.access_key == access_key,
        )

    @staticmethod
    def _checkpoint_query(scope: ExecutionScope, recipient_document: Cnpj):
        return select(FiscalDfeCheckpointORM).where(
            FiscalDfeCheckpointORM.tenant_id == scope.tenant_id,
            FiscalDfeCheckpointORM.unit_id == scope.unit_id,
            FiscalDfeCheckpointORM.environment == scope.environment.value,
            FiscalDfeCheckpointORM.recipient_document == recipient_document.value,
        )

    @staticmethod
    def _nsu_query(scope: ExecutionScope, nsu: str):
        return select(FiscalInboundDocumentORM).where(
            FiscalInboundDocumentORM.tenant_id == scope.tenant_id,
            FiscalInboundDocumentORM.unit_id == scope.unit_id,
            FiscalInboundDocumentORM.environment == scope.environment.value,
            FiscalInboundDocumentORM.nsu == nsu,
        )

    @staticmethod
    def _to_domain(row: FiscalInboundDocumentORM) -> FiscalInboundDocument:
        if row.xml_content is None:
            raise FiscalInboundStoreError("inbound document has no authoritative XML")
        parsed = parse_nfe_xml(
            scope=ExecutionScope(
                tenant_id=row.tenant_id,
                unit_id=row.unit_id,
                environment=FiscalEnvironment(row.environment),
                correlation_id=row.correlation_id,
            ),
            recipient_document=_recipient_from_xml(row.xml_content),
            xml_content=row.xml_content,
            source=FiscalInboundSource(row.source),
            discovered_at=_aware_from_db(row.discovered_at),
            nsu=row.nsu,
        )
        if parsed.inbound_id != row.inbound_id or parsed.xml_sha256 != row.xml_sha256:
            raise FiscalInboundStoreError("persisted inbound identity is inconsistent")
        return replace(parsed, status=FiscalInboundStatus(row.status))

    def _save_document(
        self,
        session: Session,
        document: FiscalInboundDocument,
    ) -> tuple[FiscalInboundDocument, bool]:
        existing = session.execute(
            self._document_query(document.scope, document.access_key.value)
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.inbound_id != document.inbound_id
                or existing.xml_sha256 != document.xml_sha256
            ):
                raise FiscalInboundConflictError(
                    "access key replay contains different inbound content"
                )
            if (
                existing.nsu is not None
                and document.nsu is not None
                and existing.nsu != document.nsu
            ):
                raise FiscalInboundConflictError(
                    "access key replay contains a different NSU"
                )
            if document.source is FiscalInboundSource.DFE and existing.nsu is None:
                same_nsu = session.execute(
                    self._nsu_query(document.scope, document.nsu or "")
                ).scalar_one_or_none()
                if same_nsu is not None:
                    raise FiscalInboundConflictError(
                        "NSU is already bound to another inbound document"
                    )
                existing.nsu = document.nsu
                existing.source = FiscalInboundSource.DFE.value
                existing.updated_at = _db_datetime(document.discovered_at)
                session.flush()
            return self._to_domain(existing), False

        if document.nsu is not None:
            same_nsu = session.execute(
                select(FiscalInboundDocumentORM).where(
                    FiscalInboundDocumentORM.tenant_id == document.scope.tenant_id,
                    FiscalInboundDocumentORM.unit_id == document.scope.unit_id,
                    FiscalInboundDocumentORM.environment
                    == document.scope.environment.value,
                    FiscalInboundDocumentORM.nsu == document.nsu,
                )
            ).scalar_one_or_none()
            if same_nsu is not None:
                raise FiscalInboundConflictError(
                    "NSU is already bound to another inbound document"
                )

        row = FiscalInboundDocumentORM(
            inbound_id=document.inbound_id,
            tenant_id=document.scope.tenant_id,
            unit_id=document.scope.unit_id,
            environment=document.scope.environment.value,
            access_key=document.access_key.value,
            nsu=document.nsu,
            issuer_document=document.issuer_document.value,
            issuer_name=document.issuer_name,
            status=document.status.value,
            source=document.source.value,
            xml_content=document.xml_content,
            xml_sha256=document.xml_sha256,
            correlation_id=document.scope.correlation_id,
            discovered_at=_db_datetime(document.discovered_at),
            updated_at=_db_datetime(document.discovered_at),
        )
        session.add(row)
        for item in document.items:
            session.add(
                FiscalInboundItemORM(
                    inbound_id=document.inbound_id,
                    line_number=item.line_number,
                    tenant_id=document.scope.tenant_id,
                    unit_id=document.scope.unit_id,
                    environment=document.scope.environment.value,
                    product_code=item.product_code,
                    description=item.description,
                    ncm=item.ncm,
                    commercial_unit=item.commercial_unit,
                    quantity=item.quantity,
                    unit_value=item.unit_value,
                    total_value=item.total_value,
                )
            )
        session.flush()
        return document, True

    def save_upload(
        self,
        document: FiscalInboundDocument,
    ) -> tuple[FiscalInboundDocument, bool]:
        if document.source is not FiscalInboundSource.XML_UPLOAD:
            raise FiscalValidationError("save_upload accepts only XML_UPLOAD documents")
        try:
            with self._session_factory() as session, session.begin():
                return self._save_document(session, document)
        except IntegrityError as exc:
            raise FiscalInboundConflictError("inbound upload identity conflict") from exc

    def save_distribution(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
        documents: Sequence[FiscalInboundDocument],
        last_nsu: str,
        max_nsu: str,
        updated_at: datetime,
    ) -> tuple[tuple[FiscalInboundDocument, ...], FiscalNsuCheckpoint]:
        normalized_last = normalize_nsu(last_nsu, "last_nsu")
        normalized_max = normalize_nsu(max_nsu, "max_nsu")
        if int(normalized_max) < int(normalized_last):
            raise FiscalValidationError("max_nsu must not precede last_nsu")
        _db_datetime(updated_at)
        for document in documents:
            if document.scope.partition_key != scope.partition_key:
                raise FiscalCheckpointConflictError(
                    "DF-e document is outside checkpoint partition"
                )
            if document.recipient_document != recipient_document:
                raise FiscalCheckpointConflictError(
                    "DF-e recipient differs from checkpoint recipient"
                )
            if document.source is not FiscalInboundSource.DFE or document.nsu is None:
                raise FiscalValidationError("distribution accepts only DF-e documents")
            if int(document.nsu) > int(normalized_last):
                raise FiscalCheckpointConflictError(
                    "document NSU exceeds batch checkpoint"
                )

        try:
            with self._session_factory() as session, session.begin():
                checkpoint = session.execute(
                    self._checkpoint_query(scope, recipient_document).with_for_update()
                ).scalar_one_or_none()
                previous = "000000000000000" if checkpoint is None else checkpoint.last_nsu
                if int(normalized_last) < int(previous):
                    raise FiscalCheckpointConflictError("DF-e checkpoint cannot regress")
                for document in documents:
                    existing_nsu = session.execute(
                        self._nsu_query(scope, document.nsu or "")
                    ).scalar_one_or_none()
                    if (
                        existing_nsu is not None
                        and existing_nsu.access_key != document.access_key.value
                    ):
                        raise FiscalInboundConflictError(
                            "DF-e NSU was replayed with a different access key"
                        )
                    if int(document.nsu or "0") <= int(previous):
                        existing = session.execute(
                            self._document_query(scope, document.access_key.value)
                        ).scalar_one_or_none()
                        if existing is None:
                            raise FiscalCheckpointConflictError(
                                "DF-e batch contains an unpersisted NSU behind checkpoint"
                            )

                saved = tuple(
                    self._save_document(session, document)[0]
                    for document in documents
                )
                if checkpoint is None:
                    checkpoint = FiscalDfeCheckpointORM(
                        tenant_id=scope.tenant_id,
                        unit_id=scope.unit_id,
                        environment=scope.environment.value,
                        recipient_document=recipient_document.value,
                        last_nsu=normalized_last,
                        max_nsu=normalized_max,
                        version=1,
                        updated_at=_db_datetime(updated_at),
                    )
                    session.add(checkpoint)
                elif (
                    checkpoint.last_nsu != normalized_last
                    or checkpoint.max_nsu != normalized_max
                ):
                    if int(normalized_max) < int(checkpoint.max_nsu or "0"):
                        raise FiscalCheckpointConflictError("DF-e max_nsu cannot regress")
                    checkpoint.last_nsu = normalized_last
                    checkpoint.max_nsu = normalized_max
                    checkpoint.version += 1
                    checkpoint.updated_at = _db_datetime(updated_at)
                session.flush()
                result_checkpoint = _checkpoint_domain(scope, recipient_document, checkpoint)
                return saved, result_checkpoint
        except IntegrityError as exc:
            raise FiscalInboundConflictError("DF-e persistence identity conflict") from exc

    def checkpoint(
        self,
        *,
        scope: ExecutionScope,
        recipient_document: Cnpj,
    ) -> FiscalNsuCheckpoint | None:
        with self._session_factory() as session:
            row = session.execute(
                self._checkpoint_query(scope, recipient_document)
            ).scalar_one_or_none()
            return None if row is None else _checkpoint_domain(scope, recipient_document, row)

    def get(
        self,
        *,
        scope: ExecutionScope,
        access_key: str,
    ) -> FiscalInboundDocument:
        with self._session_factory() as session:
            row = session.execute(
                self._document_query(scope, access_key)
            ).scalar_one_or_none()
            if row is None:
                raise FiscalInboundNotFoundError("inbound document not found")
            return self._to_domain(row)

    def list_inbox(
        self,
        *,
        scope: ExecutionScope,
        limit: int = 100,
    ) -> tuple[FiscalInboundDocument, ...]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise FiscalValidationError("limit must be an integer between 1 and 500")
        with self._session_factory() as session:
            rows = session.execute(
                select(FiscalInboundDocumentORM)
                .where(
                    FiscalInboundDocumentORM.tenant_id == scope.tenant_id,
                    FiscalInboundDocumentORM.unit_id == scope.unit_id,
                    FiscalInboundDocumentORM.environment == scope.environment.value,
                )
                .order_by(FiscalInboundDocumentORM.discovered_at.desc())
                .limit(limit)
            ).scalars()
            return tuple(self._to_domain(row) for row in rows)

    def record_manifestation(self, manifestation: FiscalManifestation) -> bool:
        try:
            with self._session_factory() as session, session.begin():
                document = session.execute(
                    self._document_query(
                        manifestation.scope,
                        manifestation.access_key.value,
                    ).with_for_update()
                ).scalar_one_or_none()
                if document is None:
                    raise FiscalInboundNotFoundError(
                        "cannot manifest an inbound document outside the partition"
                    )
                existing = session.execute(
                    select(FiscalManifestationORM).where(
                        FiscalManifestationORM.tenant_id
                        == manifestation.scope.tenant_id,
                        FiscalManifestationORM.unit_id
                        == manifestation.scope.unit_id,
                        FiscalManifestationORM.environment
                        == manifestation.scope.environment.value,
                        FiscalManifestationORM.idempotency_key
                        == manifestation.idempotency_key,
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    if (
                        existing.manifestation_id != manifestation.manifestation_id
                        or existing.access_key != manifestation.access_key.value
                        or existing.event_type != manifestation.event_type.value
                        or existing.actor_id != manifestation.actor_id
                        or existing.protocol_reference
                        != manifestation.protocol_reference
                        or existing.correlation_id != manifestation.correlation_id
                        or _aware_from_db(existing.occurred_at)
                        != _db_datetime(manifestation.occurred_at)
                    ):
                        raise FiscalInboundConflictError(
                            "manifestation replay contains different content"
                        )
                    return False
                session.add(
                    FiscalManifestationORM(
                        manifestation_id=manifestation.manifestation_id,
                        tenant_id=manifestation.scope.tenant_id,
                        unit_id=manifestation.scope.unit_id,
                        environment=manifestation.scope.environment.value,
                        access_key=manifestation.access_key.value,
                        event_type=manifestation.event_type.value,
                        idempotency_key=manifestation.idempotency_key,
                        protocol_reference=manifestation.protocol_reference,
                        actor_id=manifestation.actor_id,
                        correlation_id=manifestation.correlation_id,
                        occurred_at=_db_datetime(manifestation.occurred_at),
                    )
                )
                document.status = FiscalInboundStatus.MANIFESTED.value
                document.updated_at = _db_datetime(manifestation.occurred_at)
                session.flush()
                return True
        except IntegrityError as exc:
            raise FiscalInboundConflictError("manifestation identity conflict") from exc


def _aware_from_db(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _recipient_from_xml(xml_content: bytes) -> Cnpj:
    from xml.etree import ElementTree

    root = ElementTree.fromstring(xml_content)
    for candidate in root.iter():
        if candidate.tag.rsplit("}", 1)[-1] != "dest":
            continue
        for child in candidate:
            if child.tag.rsplit("}", 1)[-1] == "CNPJ" and child.text:
                return Cnpj(child.text)
    raise FiscalInboundStoreError("persisted inbound XML has no recipient CNPJ")


def _checkpoint_domain(
    scope: ExecutionScope,
    recipient_document: Cnpj,
    row: FiscalDfeCheckpointORM,
) -> FiscalNsuCheckpoint:
    return FiscalNsuCheckpoint(
        scope=scope,
        recipient_document=recipient_document,
        last_nsu=row.last_nsu,
        max_nsu=row.max_nsu or row.last_nsu,
        version=row.version,
        updated_at=_aware_from_db(row.updated_at),
    )
