from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from PIL import Image
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from application.fiscal_inbound import FiscalInboundApplication
from application.fiscal_intake import (
    FiscalIntakeExtractionError,
    SmartFiscalIntakeApplication,
)
from core.estoque.modelos_orm import MovimentoEstoqueORM, StockBase
from infra.fiscal.inbound_sqlalchemy import FiscalInboundStoreSQLAlchemy
from infra.fiscal.intake_ai import (
    GeminiFiscalIntakeExtractor,
    parse_fiscal_intake_extraction,
)
from infra.fiscal.intake_sqlalchemy import (
    FiscalIntakeConflictError,
    FiscalIntakeNotFoundError,
    FiscalIntakeStoreSQLAlchemy,
)
from infra.fiscal.modelos_orm import FiscalArchiveORM, FiscalBase
from kordena_fiscal.archive import RetentionPolicyMetadata
from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalEnvironment,
    FiscalValidationError,
)
from kordena_fiscal.inbound import FiscalInboundSource
from kordena_fiscal.intake import (
    FiscalIntakeArtifact,
    FiscalIntakeCandidateItem,
    FiscalIntakeExtraction,
    FiscalIntakeIssueCode,
    FiscalIntakeReconciliationStatus,
    FiscalIntakeSource,
    FiscalIntakeStatus,
)
from kordena_fiscal.xml import AccessKeyInput, NfeAccessKey, build_access_key

NOW = datetime(2026, 9, 20, 2, 0, tzinfo=timezone.utc)
CNPJ = Cnpj("11222333000181")
RETENTION = RetentionPolicyMetadata(policy_id="fiscal-evidence-v1", policy_version=1)


def _factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    FiscalBase.metadata.create_all(engine)
    StockBase.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    inbound_store = FiscalInboundStoreSQLAlchemy(sessions)
    intake_store = FiscalIntakeStoreSQLAlchemy(sessions)
    app = SmartFiscalIntakeApplication(
        store=intake_store,
        inbound_application=FiscalInboundApplication(store=inbound_store),
        inbound_store=inbound_store,
    )
    return engine, sessions, intake_store, inbound_store, app


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


def _access_key(invoice_number: int = 1) -> NfeAccessKey:
    return build_access_key(
        AccessKeyInput(
            state_ibge_code="35",
            issued_at=NOW,
            issuer_cnpj=CNPJ,
            model=ElectronicInvoiceModel.NFE,
            series=1,
            invoice_number=invoice_number,
            emission_type=1,
            numeric_code=invoice_number,
        )
    )


def _xml(invoice_number: int = 1) -> bytes:
    key = _access_key(invoice_number).value
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe><infNFe Id="NFe{key}" versao="4.00">
    <ide><dhEmi>2026-09-20T02:00:00+00:00</dhEmi></ide>
    <emit><CNPJ>{CNPJ.value}</CNPJ><xNome>Fornecedor</xNome></emit>
    <dest><CNPJ>{CNPJ.value}</CNPJ><xNome>Kordena</xNome></dest>
    <det nItem="1"><prod><cProd>P-1</cProd><xProd>Farinha</xProd>
      <NCM>11010010</NCM><uCom>KG</uCom><qCom>2.000000</qCom>
      <vUnCom>5.000000</vUnCom><vProd>10.000000</vProd>
    </prod></det>
  </infNFe></NFe>
</nfeProc>""".encode()


def _extraction(
    *,
    description: str = "Farinha",
    include_optional: bool = True,
) -> FiscalIntakeExtraction:
    return FiscalIntakeExtraction(
        access_key=_access_key() if include_optional else None,
        issuer_document=CNPJ if include_optional else None,
        recipient_document=CNPJ if include_optional else None,
        confidence=Decimal("0.98"),
        items=(
            FiscalIntakeCandidateItem(
                line_number=1,
                product_code="P-1" if include_optional else None,
                description=description,
                ncm="11010010" if include_optional else None,
                commercial_unit="KG" if include_optional else None,
                quantity=Decimal("2.000000") if include_optional else None,
                unit_value=Decimal("5.000000") if include_optional else None,
                total_value=Decimal("10.000000") if include_optional else None,
            ),
        ),
    )


@dataclass
class _Extractor:
    result: FiscalIntakeExtraction
    calls: int = 0

    def extract(self, artifact):
        self.calls += 1
        assert artifact.scope == _scope()
        return self.result


class _FailingExtractor:
    def extract(self, artifact):
        raise RuntimeError("secret provider detail must not be persisted")


def _ingest(app, extractor, *, source=FiscalIntakeSource.PDF, content=b"%PDF-1.7\n"):
    media_type = "application/pdf" if source is FiscalIntakeSource.PDF else "image/png"
    return app.ingest_preliminary(
        scope=_scope(),
        source=source,
        media_type=media_type,
        content=content,
        idempotency_key="capture:1",
        captured_at=NOW,
        retention=RETENTION,
        extractor=extractor,
    )


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (2, 2), color="white").save(output, format="PNG")
    return output.getvalue()


def test_wp031f_schema_and_atomic_archive_preserve_original_evidence() -> None:
    engine, sessions, _, _, app = _factory()
    extractor = _Extractor(_extraction())

    capture, created = _ingest(app, extractor)

    assert created
    assert capture.status is FiscalIntakeStatus.EXTRACTED
    assert "fiscal_intake_captures_v1" in inspect(engine).get_table_names()
    assert "ix_fiscal_intake_partition_status_v1" in {
        item["name"]
        for item in inspect(engine).get_indexes("fiscal_intake_captures_v1")
    }
    with sessions() as session:
        archived = session.get(FiscalArchiveORM, capture.archive_entry_id)
        assert archived is not None
        assert archived.content == b"%PDF-1.7\n"
        assert archived.document_reference == capture.capture_id


@pytest.mark.parametrize("source", [FiscalIntakeSource.IMAGE, FiscalIntakeSource.CAMERA])
def test_wp031f_image_and_camera_converge_to_same_preliminary_contract(source) -> None:
    _, _, _, _, app = _factory()
    capture, created = _ingest(app, _Extractor(_extraction()), source=source, content=_png())

    assert created
    assert capture.source is source
    assert capture.authority.value == "preliminary"


def test_wp031f_replay_skips_provider_and_changed_content_fails_closed() -> None:
    _, _, _, _, app = _factory()
    extractor = _Extractor(_extraction())
    first, created = _ingest(app, extractor)
    replay, replay_created = _ingest(app, extractor)

    assert created and not replay_created
    assert replay == first
    assert extractor.calls == 1
    with pytest.raises(FiscalIntakeConflictError):
        _ingest(app, extractor, content=b"%PDF-1.7\ndifferent")


def test_wp031f_failed_extraction_is_durable_safe_and_retryable() -> None:
    _, _, store, _, app = _factory()
    with pytest.raises(FiscalIntakeExtractionError):
        _ingest(app, _FailingExtractor())

    capture_id = next(item.capture_id for item in store.list(scope=_scope()))
    failed = store.get(scope=_scope(), capture_id=capture_id)
    assert failed.status is FiscalIntakeStatus.EXTRACTION_FAILED
    assert failed.last_error_code == "intake.extractor_unavailable"
    assert "secret" not in (failed.last_error_code or "")

    recovered, created = _ingest(app, _Extractor(_extraction()))
    assert not created
    assert recovered.status is FiscalIntakeStatus.EXTRACTED
    assert recovered.version == 3


def test_wp031f_partition_isolation_covers_tenant_unit_and_environment() -> None:
    _, _, store, _, app = _factory()
    capture, _ = _ingest(app, _Extractor(_extraction()))

    for foreign_scope in (
        _scope(tenant="tenant-b"),
        _scope(unit="unit-b"),
        _scope(environment=FiscalEnvironment.PRODUCTION),
    ):
        assert store.list(scope=foreign_scope) == ()
        with pytest.raises(FiscalIntakeNotFoundError):
            store.get(scope=foreign_scope, capture_id=capture.capture_id)


def test_wp031f_xml_is_official_reconciliation_does_not_mutate_truth_or_stock() -> None:
    _, sessions, _, inbound_store, app = _factory()
    preliminary, _ = _ingest(app, _Extractor(_extraction()))
    official, created = app.ingest_official_xml(
        scope=_scope(),
        recipient_document=CNPJ,
        xml_content=_xml(),
        received_at=NOW,
    )
    before = inbound_store.get(
        scope=_scope(),
        access_key=official.document.access_key.value,
    )

    reconciled = app.reconcile(
        scope=_scope(),
        capture_id=preliminary.capture_id,
        official_access_key=official.document.access_key.value,
        reconciled_at=NOW + timedelta(seconds=1),
    )
    after = inbound_store.get(
        scope=_scope(),
        access_key=official.document.access_key.value,
    )

    assert created
    assert official.authority.value == "official"
    assert official.source is FiscalIntakeSource.XML
    dfe_document = type(before)(
        scope=before.scope,
        access_key=before.access_key,
        recipient_document=before.recipient_document,
        issuer_document=before.issuer_document,
        issuer_name=before.issuer_name,
        issued_at=before.issued_at,
        status=before.status,
        source=FiscalInboundSource.DFE,
        xml_content=before.xml_content,
        items=before.items,
        discovered_at=before.discovered_at,
        nsu="1",
    )
    assert app.normalize_official(dfe_document).source is FiscalIntakeSource.DFE
    assert reconciled.status is FiscalIntakeStatus.RECONCILED
    assert reconciled.reconciliation is not None
    assert reconciled.reconciliation.status is FiscalIntakeReconciliationStatus.MATCHED
    assert (
        app.reconcile(
            scope=_scope(),
            capture_id=preliminary.capture_id,
            official_access_key=official.document.access_key.value,
            reconciled_at=NOW + timedelta(seconds=2),
        )
        == reconciled
    )
    assert after == before
    with sessions() as session:
        movements = session.scalar(select(func.count()).select_from(MovimentoEstoqueORM))
        assert movements == 0


@pytest.mark.parametrize(
    ("extraction", "expected_status", "expected_issue"),
    [
        (
            _extraction(include_optional=False),
            FiscalIntakeReconciliationStatus.PARTIAL,
            FiscalIntakeIssueCode.PRELIMINARY_FIELD_MISSING,
        ),
        (
            _extraction(description="Produto divergente"),
            FiscalIntakeReconciliationStatus.DIVERGENT,
            FiscalIntakeIssueCode.DESCRIPTION_MISMATCH,
        ),
    ],
)
def test_wp031f_reconciliation_classifies_partial_and_divergent(
    extraction,
    expected_status,
    expected_issue,
) -> None:
    _, _, _, _, app = _factory()
    preliminary, _ = _ingest(app, _Extractor(extraction))
    official, _ = app.ingest_official_xml(
        scope=_scope(),
        recipient_document=CNPJ,
        xml_content=_xml(),
        received_at=NOW,
    )

    result = app.reconcile(
        scope=_scope(),
        capture_id=preliminary.capture_id,
        official_access_key=official.document.access_key.value,
        reconciled_at=NOW + timedelta(seconds=1),
    )

    assert result.reconciliation is not None
    assert result.reconciliation.status is expected_status
    assert expected_issue in result.reconciliation.issues


def test_wp031f_ai_adapter_validates_pdf_image_and_structured_output() -> None:
    valid_json = """{
      "access_key": null, "issuer_document": null, "recipient_document": null,
      "confidence": 0.8,
      "items": [{"line_number": 1, "description": "Farinha",
        "product_code": null, "ncm": null, "commercial_unit": null,
        "quantity": null, "unit_value": null, "total_value": null}]
    }"""

    class _Response:
        text = valid_json

    calls = []

    def generate_content(**kwargs):
        calls.append(kwargs)
        return _Response()

    extractor = GeminiFiscalIntakeExtractor(generate_content)
    for source, media_type, content in (
        (FiscalIntakeSource.PDF, "application/pdf", b"%PDF-1.7\n"),
        (FiscalIntakeSource.IMAGE, "image/png", _png()),
        (FiscalIntakeSource.CAMERA, "image/png", _png()),
    ):
        result = extractor.extract(
            FiscalIntakeArtifact(
                scope=_scope(),
                source=source,
                media_type=media_type,
                content=content,
                idempotency_key=f"media:{source.value}",
                captured_at=NOW,
            )
        )
        assert result.items[0].description == "Farinha"
    assert len(calls) == 3

    with pytest.raises(FiscalValidationError):
        parse_fiscal_intake_extraction("not-json")
    with pytest.raises(FiscalValidationError):
        parse_fiscal_intake_extraction(
            '{"confidence": 0.5, "items": [], "unexpected": true}'
        )

    invalid_pdf = FiscalIntakeArtifact(
        scope=_scope(),
        source=FiscalIntakeSource.PDF,
        media_type="application/pdf",
        content=b"not a pdf",
        idempotency_key="invalid-pdf",
        captured_at=NOW,
    )
    with pytest.raises(FiscalValidationError):
        extractor.extract(invalid_pdf)


def test_wp031f_rejects_invalid_media_and_oversized_content_before_provider() -> None:
    _, _, _, _, app = _factory()
    extractor = _Extractor(_extraction())

    with pytest.raises(FiscalValidationError):
        app.ingest_preliminary(
            scope=_scope(),
            source=FiscalIntakeSource.PDF,
            media_type="image/png",
            content=b"invalid",
            idempotency_key="bad-media",
            captured_at=NOW,
            retention=RETENTION,
            extractor=extractor,
        )
    with pytest.raises(FiscalValidationError):
        app.ingest_preliminary(
            scope=_scope(),
            source=FiscalIntakeSource.PDF,
            media_type="application/pdf",
            content=b"x" * (10 * 1024 * 1024 + 1),
            idempotency_key="too-large",
            captured_at=NOW,
            retention=RETENTION,
            extractor=extractor,
        )
    assert extractor.calls == 0
