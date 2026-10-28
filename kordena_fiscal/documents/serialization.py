"""Deterministic serialization for canonical fiscal documents."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from kordena_fiscal.domain import FiscalProductProfile, FiscalProfile, Money
from kordena_fiscal.tax import RestaurantSupplyDecision, TaxDecision

from .models import CanonicalFiscalDocument, FiscalLineSnapshot, FiscalPaymentSnapshot


def _decimal_text(value: Decimal) -> str:
    """Produce one non-exponential canonical textual representation."""

    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _money(value: Money) -> dict[str, str]:
    return {"amount": _decimal_text(value.amount), "currency": value.currency}


def _instant(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.astimezone(UTC).isoformat(timespec="microseconds")
    return normalized.replace("+00:00", "Z")


def _issuer(profile: FiscalProfile) -> dict[str, Any]:
    address = profile.address
    return {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "cnpj": profile.cnpj.value,
        "legal_name": profile.legal_name,
        "trade_name": profile.trade_name,
        "tax_regime": int(profile.tax_regime),
        "state_registration": {
            "state_code": profile.state_registration.state_code,
            "number": profile.state_registration.number,
            "exempt": profile.state_registration.exempt,
        },
        "municipal_registration": (
            profile.municipal_registration.number
            if profile.municipal_registration is not None
            else None
        ),
        "primary_cnae": profile.primary_cnae.value,
        "address": {
            "street": address.street,
            "number": address.number,
            "district": address.district,
            "municipality_name": address.municipality_name,
            "municipality_ibge_code": address.jurisdiction.municipality_ibge_code,
            "state_code": address.jurisdiction.state_code,
            "country_code": address.jurisdiction.country_code,
            "postal_code": address.postal_code,
            "complement": address.complement,
        },
        "effective_from": _instant(profile.effective_from),
        "effective_to": _instant(profile.effective_to),
    }


def _product(profile: FiscalProductProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "product_id": profile.product_id,
        "version": profile.version,
        "commercial_code": profile.commercial_code,
        "description": profile.description,
        "ncm": profile.ncm.value,
        "cest": profile.cest.value if profile.cest is not None else None,
        "commercial_unit": profile.commercial_unit.value,
        "taxable_unit": profile.taxable_unit.value,
        "origin": int(profile.origin),
        "gtin": profile.gtin.value if profile.gtin is not None else None,
        "hints": {
            "fiscal_benefit_code": profile.hints.fiscal_benefit_code,
            "ibs_cbs_classification_code": profile.hints.ibs_cbs_classification_code,
        },
        "effective_from": _instant(profile.effective_from),
        "effective_to": _instant(profile.effective_to),
    }


def _tax_decision(decision: TaxDecision) -> dict[str, Any]:
    outcome = decision.outcome
    return {
        "rule_id": decision.rule_id,
        "rule_version": decision.rule_version,
        "source_normative": decision.source_normative,
        "rank": list(decision.rank),
        "outcome": {
            "cfop": outcome.cfop,
            "icms_code": outcome.icms_code,
            "pis_cst": outcome.pis_cst,
            "cofins_cst": outcome.cofins_cst,
            "ibs_cbs_classification_code": outcome.ibs_cbs_classification_code,
            "legal_notes": list(outcome.legal_notes),
        },
    }


def _restaurant_decision(
    decision: RestaurantSupplyDecision | None,
) -> dict[str, Any] | None:
    if decision is None:
        return None
    return {
        "treatment": decision.treatment.value,
        "reason_code": decision.reason_code,
        "normative_references": list(decision.normative_references),
        "rate_reduction_percent": (
            _decimal_text(decision.rate_reduction_percent)
            if decision.rate_reduction_percent is not None
            else None
        ),
        "recipient_credit_allowed": decision.recipient_credit_allowed,
    }


def _line(line: FiscalLineSnapshot) -> dict[str, Any]:
    return {
        "line_number": line.line_number,
        "product": _product(line.product),
        "quantity": _decimal_text(line.quantity),
        "unit_price": _money(line.unit_price),
        "gross_amount": _money(line.gross_amount),
        "discount_amount": _money(line.discount_amount),
        "surcharge_amount": _money(line.surcharge_amount),
        "net_amount": _money(line.net_amount),
        "tax_decision": _tax_decision(line.tax_decision),
        "restaurant_decision": _restaurant_decision(line.restaurant_decision),
    }


def _payment(payment: FiscalPaymentSnapshot) -> dict[str, Any]:
    return {
        "method": payment.method.value,
        "amount": _money(payment.amount),
        "provider_reference": payment.provider_reference,
    }


def to_canonical_payload(document: CanonicalFiscalDocument) -> dict[str, Any]:
    """Return a JSON-safe canonical snapshot without provider/XML assumptions."""

    totals = document.totals
    return {
        "schema_version": document.schema_version,
        "document_id": document.document_id,
        "scope": {
            "tenant_id": document.scope.tenant_id,
            "unit_id": document.scope.unit_id,
            "environment": document.scope.environment.value,
            "correlation_id": document.scope.correlation_id,
        },
        "source": {
            "source_type": document.source.source_type,
            "source_id": document.source.source_id,
        },
        "document_kind": document.document_kind.value,
        "issued_at": _instant(document.issued_at),
        "issuer": _issuer(document.issuer),
        "items": [_line(item) for item in document.items],
        "payments": [_payment(payment) for payment in document.payments],
        "totals": {
            "gross_amount": _money(totals.gross_amount),
            "discount_amount": _money(totals.discount_amount),
            "surcharge_amount": _money(totals.surcharge_amount),
            "net_amount": _money(totals.net_amount),
            "payment_amount": _money(totals.payment_amount),
            "change_amount": _money(totals.change_amount),
        },
    }


def to_canonical_json(document: CanonicalFiscalDocument) -> str:
    """Serialize deterministically for audit/fingerprint use."""

    return json.dumps(
        to_canonical_payload(document),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_sha256(document: CanonicalFiscalDocument) -> str:
    """Return a stable content fingerprint, not an authorization/access key."""

    encoded = to_canonical_json(document).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
