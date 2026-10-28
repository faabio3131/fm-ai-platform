"""Deterministic reconciliation without mutating official fiscal truth."""

from __future__ import annotations

import unicodedata
from datetime import datetime

from kordena_fiscal.domain import FiscalValidationError
from kordena_fiscal.inbound import FiscalInboundDocument

from .models import (
    FiscalIntakeCapture,
    FiscalIntakeIssueCode,
    FiscalIntakeReconciliation,
    FiscalIntakeReconciliationStatus,
)


def _text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(normalized.encode("ascii", "ignore").decode().casefold().split())


def reconcile_fiscal_intake(
    capture: FiscalIntakeCapture,
    document: FiscalInboundDocument,
    *,
    reconciled_at: datetime,
) -> FiscalIntakeReconciliation:
    if capture.scope.partition_key != document.scope.partition_key:
        raise FiscalValidationError("intake and official document cross partitions")
    if capture.extraction is None:
        raise FiscalValidationError("intake capture has no extraction to reconcile")

    extraction = capture.extraction
    issues: set[FiscalIntakeIssueCode] = set()
    missing = False

    for header_candidate, header_official, header_code in (
        (extraction.access_key, document.access_key, FiscalIntakeIssueCode.ACCESS_KEY_MISMATCH),
        (
            extraction.issuer_document,
            document.issuer_document,
            FiscalIntakeIssueCode.ISSUER_MISMATCH,
        ),
        (
            extraction.recipient_document,
            document.recipient_document,
            FiscalIntakeIssueCode.RECIPIENT_MISMATCH,
        ),
    ):
        if header_candidate is None:
            missing = True
        elif header_candidate != header_official:
            issues.add(header_code)

    if len(extraction.items) != len(document.items):
        issues.add(FiscalIntakeIssueCode.ITEM_COUNT_MISMATCH)

    for candidate_item, official_item in zip(
        extraction.items,
        document.items,
        strict=False,
    ):
        if _text(candidate_item.description) != _text(official_item.description):
            issues.add(FiscalIntakeIssueCode.DESCRIPTION_MISMATCH)
        comparisons = (
            (
                candidate_item.product_code,
                official_item.product_code,
                FiscalIntakeIssueCode.PRODUCT_CODE_MISMATCH,
                False,
            ),
            (
                candidate_item.ncm,
                official_item.ncm,
                FiscalIntakeIssueCode.NCM_MISMATCH,
                False,
            ),
            (
                candidate_item.commercial_unit,
                official_item.commercial_unit,
                FiscalIntakeIssueCode.COMMERCIAL_UNIT_MISMATCH,
                False,
            ),
            (
                candidate_item.quantity,
                official_item.quantity,
                FiscalIntakeIssueCode.QUANTITY_MISMATCH,
                True,
            ),
            (
                candidate_item.unit_value,
                official_item.unit_value,
                FiscalIntakeIssueCode.UNIT_VALUE_MISMATCH,
                True,
            ),
            (
                candidate_item.total_value,
                official_item.total_value,
                FiscalIntakeIssueCode.TOTAL_VALUE_MISMATCH,
                True,
            ),
        )
        for candidate_value, official_value, code, _numeric in comparisons:
            if candidate_value is None:
                missing = True
            elif candidate_value != official_value:
                issues.add(code)

    if issues:
        status = FiscalIntakeReconciliationStatus.DIVERGENT
    elif missing:
        status = FiscalIntakeReconciliationStatus.PARTIAL
        issues.add(FiscalIntakeIssueCode.PRELIMINARY_FIELD_MISSING)
    else:
        status = FiscalIntakeReconciliationStatus.MATCHED

    return FiscalIntakeReconciliation(
        status=status,
        official_access_key=document.access_key,
        issues=tuple(sorted(issues, key=lambda item: item.value)),
        reconciled_at=reconciled_at,
    )
