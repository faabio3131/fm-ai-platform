"""Translate immutable Kordena fiscal outbox snapshots to NFCore Bridge v1.

No tax calculation or fallback fiscal classification occurs here.
Contract: faabio3131/nf-core-v001/contracts/v1/schemas/fm-fiscal.schema.json.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from kordena_fiscal.contingency import FiscalOutboxEntry


class NfcoreFiscalPayloadInvalid(ValueError):
    """An immutable fiscal snapshot cannot be sent to NFCore safely."""


def _object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NfcoreFiscalPayloadInvalid(f"{name} must be an object")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NfcoreFiscalPayloadInvalid(f"{name} must be a nonempty string")
    return value.strip()


def _money(value: Any, name: str) -> dict[str, str]:
    item = _object(value, name)
    if item.get("currency") != "BRL":
        raise NfcoreFiscalPayloadInvalid(f"{name} must be BRL")
    raw = _text(item.get("amount"), name)
    try:
        amount = Decimal(raw)
    except InvalidOperation as exc:
        raise NfcoreFiscalPayloadInvalid(f"{name} amount invalid") from exc
    if not amount.is_finite() or amount < 0:
        raise NfcoreFiscalPayloadInvalid(f"{name} must be nonnegative and finite")
    return {"amount": format(amount, "f"), "currency": "BRL"}


def to_nfcore_issuance(entry: FiscalOutboxEntry) -> dict[str, Any]:
    """Explicit mapping from source-bound snapshot to official request schema."""
    if entry.operation != "nfce.issue":
        raise NfcoreFiscalPayloadInvalid("unsupported fiscal outbox operation")
    try:
        document = _object(json.loads(entry.payload), "document")
    except (ValueError, UnicodeError) as exc:
        raise NfcoreFiscalPayloadInvalid("invalid fiscal outbox JSON") from exc
    scope = _object(document.get("scope"), "scope")
    expected_scope = {
        "tenant_id": entry.scope.tenant_id,
        "unit_id": entry.scope.unit_id,
        "environment": entry.scope.environment.value,
        "correlation_id": entry.scope.correlation_id,
    }
    if any(scope.get(name) != value for name, value in expected_scope.items()):
        raise NfcoreFiscalPayloadInvalid("fiscal outbox scope mismatch")
    if document.get("document_kind") != "nfce":
        raise NfcoreFiscalPayloadInvalid("only NFC-e is allowed for this operation")
    source = _object(document.get("source"), "source")
    if source.get("source_type") != "venda":
        raise NfcoreFiscalPayloadInvalid("fiscal source must be canonical sale")
    sale_id = _text(source.get("source_id"), "sale id")
    issued_at = _text(document.get("issued_at"), "occurred_at")
    totals = _object(document.get("totals"), "totals")
    money = {
        name: _money(totals.get(name), name)
        for name in (
            "gross_amount",
            "discount_amount",
            "surcharge_amount",
            "net_amount",
            "payment_amount",
            "change_amount",
        )
    }
    gross = Decimal(money["gross_amount"]["amount"])
    discount = Decimal(money["discount_amount"]["amount"])
    surcharge = Decimal(money["surcharge_amount"]["amount"])
    net = Decimal(money["net_amount"]["amount"])
    paid = Decimal(money["payment_amount"]["amount"])
    change = Decimal(money["change_amount"]["amount"])
    if net <= 0 or gross - discount + surcharge != net or paid - change != net:
        raise NfcoreFiscalPayloadInvalid("fiscal totals do not reconcile")

    lines = document.get("items")
    if not isinstance(lines, list) or not lines:
        raise NfcoreFiscalPayloadInvalid("fiscal document has no lines")
    result_lines = []
    total_lines = Decimal("0")
    for raw in lines:
        line = _object(raw, "line")
        product = _object(line.get("product"), "product")
        product_id = _text(product.get("product_id"), "product_id")
        desc = _text(product.get("description"), "description")
        number = line.get("line_number")
        if type(number) is not int or number < 1:
            raise NfcoreFiscalPayloadInvalid("line number invalid")
        quantity = _text(line.get("quantity"), "quantity")
        try:
            quantity_value = Decimal(quantity)
        except InvalidOperation as exc:
            raise NfcoreFiscalPayloadInvalid("quantity invalid") from exc
        if not quantity_value.is_finite() or quantity_value <= 0:
            raise NfcoreFiscalPayloadInvalid("quantity must be positive")
        unit_price = _money(line.get("unit_price"), "unit_price")
        gross_line = _money(line.get("gross_amount"), "gross_amount")
        discount_line = _money(line.get("discount_amount"), "discount_amount")
        surcharge_line = _money(line.get("surcharge_amount"), "surcharge_amount")
        net_line = (
            Decimal(gross_line["amount"])
            - Decimal(discount_line["amount"])
            + Decimal(surcharge_line["amount"])
        )
        if net_line < 0:
            raise NfcoreFiscalPayloadInvalid("negative fiscal line")
        total_lines += net_line
        result_lines.append({
            "line_id": hashlib.sha256(
                f"{sale_id}:{number}".encode("utf-8")
            ).hexdigest(),
            "item_reference": {"type": "produto", "id": product_id},
            "description": desc,
            "quantity": format(quantity_value, "f"),
            "unit_price": unit_price,
            "discount_amount": discount_line,
            "surcharge_amount": surcharge_line,
        })
    if total_lines != net:
        raise NfcoreFiscalPayloadInvalid("line total does not reconcile")

    payments = document.get("payments")
    if not isinstance(payments, list) or not payments:
        raise NfcoreFiscalPayloadInvalid("fiscal document has no payments")
    result_payments = []
    paid_lines = Decimal("0")
    for raw in payments:
        payment = _object(raw, "payment")
        amount = _money(payment.get("amount"), "payment amount")
        paid_lines += Decimal(amount["amount"])
        result_payments.append({
            "method": _text(payment.get("method"), "payment method"),
            "amount": amount,
            "reference": payment.get("provider_reference"),
        })
    if paid_lines != paid:
        raise NfcoreFiscalPayloadInvalid("payment totals do not reconcile")

    return {
        "contract_version": "1.0.0",
        "operation": {
            "operation_reference": {"type": "venda", "id": sale_id},
            "operation_kind": "sale",
            "occurred_at": issued_at,
            "settled_at": issued_at,
            "totals": {
                name: money[name] for name in (
                    "gross_amount",
                    "discount_amount",
                    "surcharge_amount",
                    "net_amount",
                )
            },
            "payments": result_payments,
            "change_amount": money["change_amount"],
        },
        "document": {"kind": "nfce", "items": result_lines},
    }
