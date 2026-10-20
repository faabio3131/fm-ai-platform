from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from infra.fiscal.modelos_orm import FiscalBase
from infra.fiscal.repositorios_sqlalchemy import (
    FiscalArchiveStoreSQLAlchemy,
    FiscalOutboxStoreSQLAlchemy,
    FiscalSequenceStoreSQLAlchemy,
    IdempotencyStoreSQLAlchemy,
)
from kordena_fiscal.archive import (
    FiscalArchiveEntry,
    FiscalArchiveKind,
    RetentionPolicyMetadata,
)
from kordena_fiscal.contingency import (
    FiscalOutboxService,
    FiscalOutboxStatus,
)
from kordena_fiscal.domain import (
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
)
from kordena_fiscal.lifecycle import (
    IdempotencyKey,
    IssuanceAttemptStatus,
)
from kordena_fiscal.numbering import (
    FiscalSequenceKey,
    FiscalSequencePolicy,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _scope(tenant: str = "tenant-a", unit: str = "unit-a") -> ExecutionScope:
    return ExecutionScope(
        tenant_id=tenant,
        unit_id=unit,
        environment=FiscalEnvironment.HOMOLOGATION,
        correlation_id=f"corr-{tenant}-{unit}",
    )


def test_fiscal_persistence_schema_contains_foundation_tables() -> None:
    engine, _ = _factory()
    tables = set(inspect(engine).get_table_names())
    assert {
        "fiscal_sequences_v1",
        "fiscal_idempotency_v1",
        "fiscal_outbox_v1",
        "fiscal_archive_v1",
        "fiscal_document_projection_v1",
        "fiscal_inbound_documents_v1",
        "fiscal_dfe_checkpoint_v1",
        "fiscal_manifestations_v1",
        "fiscal_product_bindings_v1",
        "fiscal_issuer_profiles_v1",
    }.issubset(tables)


def test_sequence_is_durable_incremental_and_scope_isolated() -> None:
    _, sessions = _factory()
    store = FiscalSequenceStoreSQLAlchemy(sessions)
    policy = FiscalSequencePolicy(first_number=1, max_number=999)
    key_a = FiscalSequenceKey.from_scope(
        _scope(),
        model=ElectronicInvoiceModel.NFCE,
        series=1,
    )
    key_b = FiscalSequenceKey.from_scope(
        _scope("tenant-b", "unit-b"),
        model=ElectronicInvoiceModel.NFCE,
        series=1,
    )

    first = store.reserve_next(key_a, policy)
    second = store.reserve_next(key_a, policy)
    isolated = store.reserve_next(key_b, policy)

    assert (first.number, second.number, isolated.number) == (1, 2, 1)
    assert first.reservation_token != second.reservation_token
    assert store.last_reserved(key_a) == 2
    assert store.last_reserved(key_b) == 1


def test_idempotency_replays_and_preserves_terminal_result() -> None:
    _, sessions = _factory()
    store = IdempotencyStoreSQLAlchemy(sessions)
    key = IdempotencyKey("a" * 64)

    created = store.reserve(key, "b" * 64, "doc-1")
    replay = store.reserve(key, "b" * 64, "doc-1")
    authorized = store.mark_authorized(key, 1, "protocol-1")
    replay_authorized = store.mark_authorized(key, 1, "protocol-1")

    assert not created.replay
    assert replay.replay
    assert authorized.status is IssuanceAttemptStatus.AUTHORIZED
    assert replay_authorized == authorized
    assert len(store.attempts(key)) == 1


def test_outbox_replay_lease_retry_and_success_are_durable() -> None:
    _, sessions = _factory()
    store = FiscalOutboxStoreSQLAlchemy(sessions)
    service = FiscalOutboxService(store)
    scope = _scope()

    first = service.enqueue(
        scope=scope,
        operation="issue",
        deduplication_key="sale-1",
        payload=b'{"sale":"1"}',
        created_at=NOW,
    )
    replay = service.enqueue(
        scope=scope,
        operation="issue",
        deduplication_key="sale-1",
        payload=b'{"sale":"1"}',
        created_at=NOW,
    )
    claimed = store.claim_due(
        now=NOW,
        limit=10,
        lease_duration=timedelta(seconds=30),
    )
    retried = store.reschedule(
        claimed[0].entry_id,
        expected_attempt=1,
        available_at=NOW + timedelta(seconds=5),
        error="temporary",
    )
    claimed_again = store.claim_due(
        now=NOW + timedelta(seconds=5),
        limit=10,
        lease_duration=timedelta(seconds=30),
    )
    succeeded = store.mark_succeeded(
        claimed_again[0].entry_id,
        expected_attempt=2,
        completion_reference="protocol-1",
    )

    assert not first.replay
    assert replay.replay
    assert retried.status is FiscalOutboxStatus.RETRY_WAIT
    assert succeeded.status is FiscalOutboxStatus.SUCCEEDED
    assert succeeded.completion_reference == "protocol-1"


def test_archive_is_append_only_and_scope_filtered() -> None:
    _, sessions = _factory()
    store = FiscalArchiveStoreSQLAlchemy(sessions)
    retention = RetentionPolicyMetadata(
        policy_id="fiscal-default",
        policy_version=1,
    )
    entry = FiscalArchiveEntry.build(
        scope=_scope(),
        document_reference="doc-1",
        kind=FiscalArchiveKind.AUTHORIZED_XML,
        content=b"<xml>synthetic</xml>",
        media_type="application/xml",
        archived_at=NOW,
        retention=retention,
    )

    saved = store.append(entry)
    replay = store.append(entry)
    same_scope = store.list_for_document(_scope(), "doc-1")
    other_scope = store.list_for_document(
        _scope("tenant-b", "unit-b"),
        "doc-1",
    )

    assert saved == replay == entry
    assert same_scope == (entry,)
    assert other_scope == ()
