from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from application.fiscal_inbound import FiscalInboundApplication
from infra.fiscal.inbound_sqlalchemy import (
    FiscalCheckpointConflictError,
    FiscalInboundConflictError,
    FiscalInboundNotFoundError,
    FiscalInboundStoreSQLAlchemy,
)
from infra.fiscal.modelos_orm import (
    FiscalBase,
    FiscalInboundItemORM,
    FiscalManifestationORM,
)
from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from kordena_fiscal.inbound import (
    DfeDistributionBatch,
    DfeDistributionEntry,
    FiscalManifestationType,
)
from kordena_fiscal.xml import AccessKeyInput, build_access_key

NOW = datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc)
CNPJ = Cnpj("11222333000181")


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


def _scope(
    tenant: str = "tenant-a",
    unit: str = "unit-a",
    environment: FiscalEnvironment = FiscalEnvironment.HOMOLOGATION,
) -> ExecutionScope:
    return ExecutionScope(
        tenant_id=tenant,
        unit_id=unit,
        environment=environment,
        correlation_id=f"corr-{tenant}-{unit}-{environment.value}",
    )


def _access_key(
    invoice_number: int = 1,
    model: ElectronicInvoiceModel = ElectronicInvoiceModel.NFE,
):
    return build_access_key(
        AccessKeyInput(
            state_ibge_code="35",
            issued_at=NOW,
            issuer_cnpj=CNPJ,
            model=model,
            series=1,
            invoice_number=invoice_number,
            emission_type=1,
            numeric_code=invoice_number,
        )
    )


def _xml(
    invoice_number: int = 1,
    *,
    product: str = "Farinha",
    model: ElectronicInvoiceModel = ElectronicInvoiceModel.NFE,
) -> bytes:
    key = _access_key(invoice_number, model).value
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe{key}" versao="4.00">
      <ide><dhEmi>2026-09-20T01:00:00+00:00</dhEmi></ide>
      <emit><CNPJ>{CNPJ.value}</CNPJ><xNome>Fornecedor Teste Ltda</xNome></emit>
      <dest><CNPJ>{CNPJ.value}</CNPJ><xNome>Kordena Teste Ltda</xNome></dest>
      <det nItem="1"><prod><cProd>P-1</cProd><xProd>{product}</xProd><NCM>11010010</NCM><uCom>KG</uCom><qCom>2.000000</qCom><vUnCom>5.000000</vUnCom><vProd>10.000000</vProd></prod></det>
    </infNFe>
  </NFe>
</nfeProc>""".encode()


@dataclass
class _Adapter:
    batch: DfeDistributionBatch
    expected_after: str

    def distribute(self, *, scope, recipient_document, after_nsu):
        assert isinstance(scope, ExecutionScope)
        assert recipient_document == CNPJ
        assert after_nsu == self.expected_after
        return self.batch


def _batch(*entries: tuple[str, bytes], last: str, maximum: str = "9"):
    return DfeDistributionBatch(
        entries=tuple(
            DfeDistributionEntry(nsu=nsu, xml_content=content)
            for nsu, content in entries
        ),
        last_nsu=last,
        max_nsu=maximum,
        fetched_at=NOW,
    )


def test_wp031e_schema_adds_inbound_items_and_partition_indexes() -> None:
    engine, _ = _factory()
    tables = set(inspect(engine).get_table_names())
    assert "fiscal_inbound_items_v1" in tables
    assert "ix_fiscal_inbound_partition_status_v1" in {
        item["name"]
        for item in inspect(engine).get_indexes("fiscal_inbound_documents_v1")
    }
    assert "ix_fiscal_manifestation_partition_document_v1" in {
        item["name"]
        for item in inspect(engine).get_indexes("fiscal_manifestations_v1")
    }


def test_wp031e_dfe_batch_is_atomic_durable_and_replay_safe() -> None:
    engine, sessions = _factory()
    store = FiscalInboundStoreSQLAlchemy(sessions)
    app = FiscalInboundApplication(store=store)
    batch = _batch(("1", _xml()), last="1")

    documents, checkpoint = app.synchronize_dfe(
        scope=_scope(),
        recipient_document=CNPJ,
        adapter=_Adapter(batch, "000000000000000"),
    )
    replay, replay_checkpoint = app.synchronize_dfe(
        scope=_scope(),
        recipient_document=CNPJ,
        adapter=_Adapter(batch, "000000000000001"),
    )

    assert documents == replay
    assert checkpoint == replay_checkpoint
    assert checkpoint.last_nsu == "000000000000001"
    assert checkpoint.version == 1
    assert app.list_inbox(scope=_scope()) == documents
    with sessions() as session:
        items = session.execute(select(FiscalInboundItemORM)).scalars().all()
        assert len(items) == 1
        assert items[0].description == "Farinha"
        assert str(items[0].total_value) == "10.000000"
        assert inspect(engine).get_table_names()


def test_wp031e_access_key_and_nsu_replays_with_different_content_fail_closed() -> None:
    _, sessions = _factory()
    app = FiscalInboundApplication(store=FiscalInboundStoreSQLAlchemy(sessions))
    first = _batch(("1", _xml()), last="1")
    app.synchronize_dfe(
        scope=_scope(),
        recipient_document=CNPJ,
        adapter=_Adapter(first, "000000000000000"),
    )

    divergent = _batch(("1", _xml(product="Produto divergente")), last="1")
    with pytest.raises(FiscalInboundConflictError):
        app.synchronize_dfe(
            scope=_scope(),
            recipient_document=CNPJ,
            adapter=_Adapter(divergent, "000000000000001"),
        )

    same_nsu_other_key = _batch(("1", _xml(2)), last="1")
    with pytest.raises(FiscalInboundConflictError):
        app.synchronize_dfe(
            scope=_scope(),
            recipient_document=CNPJ,
            adapter=_Adapter(same_nsu_other_key, "000000000000001"),
        )


def test_wp031e_xml_upload_converges_to_dfe_without_duplicate_document() -> None:
    _, sessions = _factory()
    app = FiscalInboundApplication(store=FiscalInboundStoreSQLAlchemy(sessions))
    uploaded, created = app.ingest_xml_upload(
        scope=_scope(),
        recipient_document=CNPJ,
        xml_content=_xml(),
        received_at=NOW,
    )

    distributed, checkpoint = app.synchronize_dfe(
        scope=_scope(),
        recipient_document=CNPJ,
        adapter=_Adapter(_batch(("1", _xml()), last="1"), "000000000000000"),
    )

    assert created
    assert distributed[0].inbound_id == uploaded.inbound_id
    assert distributed[0].source.value == "dfe"
    assert distributed[0].nsu == "000000000000001"
    assert checkpoint.last_nsu == "000000000000001"
    assert len(app.list_inbox(scope=_scope())) == 1


def test_wp031e_failed_batch_rolls_back_documents_and_checkpoint() -> None:
    _, sessions = _factory()
    store = FiscalInboundStoreSQLAlchemy(sessions)
    app = FiscalInboundApplication(store=store)
    conflicting_batch = _batch(
        ("1", _xml()),
        ("2", _xml()),
        last="2",
    )

    with pytest.raises(FiscalInboundConflictError):
        app.synchronize_dfe(
            scope=_scope(),
            recipient_document=CNPJ,
            adapter=_Adapter(conflicting_batch, "000000000000000"),
        )

    assert app.list_inbox(scope=_scope()) == ()
    assert store.checkpoint(scope=_scope(), recipient_document=CNPJ) is None


def test_wp031e_checkpoint_rejects_regression_and_preserves_previous_state() -> None:
    _, sessions = _factory()
    store = FiscalInboundStoreSQLAlchemy(sessions)
    app = FiscalInboundApplication(store=store)
    app.synchronize_dfe(
        scope=_scope(),
        recipient_document=CNPJ,
        adapter=_Adapter(_batch(("2", _xml()), last="2"), "000000000000000"),
    )

    with pytest.raises(FiscalCheckpointConflictError):
        store.save_distribution(
            scope=_scope(),
            recipient_document=CNPJ,
            documents=(),
            last_nsu="1",
            max_nsu="9",
            updated_at=NOW,
        )
    checkpoint = store.checkpoint(scope=_scope(), recipient_document=CNPJ)
    assert checkpoint is not None
    assert checkpoint.last_nsu == "000000000000002"


def test_wp031e_partition_isolation_covers_tenant_unit_and_environment() -> None:
    _, sessions = _factory()
    store = FiscalInboundStoreSQLAlchemy(sessions)
    app = FiscalInboundApplication(store=store)
    document, created = app.ingest_xml_upload(
        scope=_scope(),
        recipient_document=CNPJ,
        xml_content=_xml(),
        received_at=NOW,
    )
    assert created
    assert app.list_inbox(scope=_scope()) == (document,)

    for foreign_scope in (
        _scope(tenant="tenant-b"),
        _scope(unit="unit-b"),
        _scope(environment=FiscalEnvironment.PRODUCTION),
    ):
        assert app.list_inbox(scope=foreign_scope) == ()
        with pytest.raises(FiscalInboundNotFoundError):
            store.get(scope=foreign_scope, access_key=document.access_key.value)


def test_wp031e_manifestation_is_partition_bound_and_replay_safe() -> None:
    _, sessions = _factory()
    store = FiscalInboundStoreSQLAlchemy(sessions)
    app = FiscalInboundApplication(store=store)
    document, _ = app.ingest_xml_upload(
        scope=_scope(),
        recipient_document=CNPJ,
        xml_content=_xml(),
        received_at=NOW,
    )

    assert app.manifest(
        scope=_scope(),
        access_key=document.access_key,
        event_type=FiscalManifestationType.ACKNOWLEDGEMENT,
        idempotency_key="manifest:1",
        actor_id="owner-a",
        occurred_at=NOW,
    )
    assert not app.manifest(
        scope=_scope(),
        access_key=document.access_key,
        event_type=FiscalManifestationType.ACKNOWLEDGEMENT,
        idempotency_key="manifest:1",
        actor_id="owner-a",
        occurred_at=NOW,
    )
    with pytest.raises(FiscalInboundConflictError):
        app.manifest(
            scope=_scope(),
            access_key=document.access_key,
            event_type=FiscalManifestationType.ACKNOWLEDGEMENT,
            idempotency_key="manifest:1",
            actor_id="owner-a",
            occurred_at=NOW.replace(hour=2),
        )
    with sessions() as session:
        assert len(session.execute(select(FiscalManifestationORM)).scalars().all()) == 1

    with pytest.raises(FiscalInboundNotFoundError):
        app.manifest(
            scope=_scope(tenant="tenant-b"),
            access_key=document.access_key,
            event_type=FiscalManifestationType.ACKNOWLEDGEMENT,
            idempotency_key="manifest:foreign",
            actor_id="owner-b",
            occurred_at=NOW,
        )


def test_wp031e_invalid_xml_recipient_and_types_fail_closed() -> None:
    _, sessions = _factory()
    app = FiscalInboundApplication(store=FiscalInboundStoreSQLAlchemy(sessions))

    padded_doctype = b" " * 5000 + b"<!DOCTYPE x><x/>"
    for invalid_xml in (b"<broken", b"<!DOCTYPE x><x/>", padded_doctype):
        with pytest.raises(FiscalValidationError):
            app.ingest_xml_upload(
                scope=_scope(),
                recipient_document=CNPJ,
                xml_content=invalid_xml,
                received_at=NOW,
            )

    with pytest.raises(FiscalValidationError, match="recipient"):
        app.ingest_xml_upload(
            scope=_scope(),
            recipient_document=Cnpj("19131243000197"),
            xml_content=_xml(),
            received_at=NOW,
        )
    with pytest.raises(FiscalValidationError, match="model 55"):
        app.ingest_xml_upload(
            scope=_scope(),
            recipient_document=CNPJ,
            xml_content=_xml(model=ElectronicInvoiceModel.NFCE),
            received_at=NOW,
        )
    with pytest.raises(FiscalValidationError, match="timezone-aware"):
        app.ingest_xml_upload(
            scope=_scope(),
            recipient_document=CNPJ,
            xml_content=_xml(),
            received_at=NOW.replace(tzinfo=None),
        )
    with pytest.raises(FiscalValidationError, match="limit"):
        app.list_inbox(scope=_scope(), limit=True)
