"""Deterministic NF-e XML parser for the inbound foundation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from kordena_fiscal.domain import (
    Cnpj,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalValidationError,
)
from kordena_fiscal.xml import NfeAccessKey

from .models import (
    FiscalInboundDocument,
    FiscalInboundItem,
    FiscalInboundSource,
    FiscalInboundStatus,
)

_MAX_XML_BYTES = 10 * 1024 * 1024


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(parent: ElementTree.Element, name: str) -> ElementTree.Element:
    for candidate in parent:
        if _local_name(candidate.tag) == name:
            return candidate
    raise FiscalValidationError(f"NF-e XML is missing {name}")


def _descendant(parent: ElementTree.Element, name: str) -> ElementTree.Element:
    for candidate in parent.iter():
        if _local_name(candidate.tag) == name:
            return candidate
    raise FiscalValidationError(f"NF-e XML is missing {name}")


def _text(parent: ElementTree.Element, name: str, *, max_length: int) -> str:
    value = (_child(parent, name).text or "").strip()
    if not value:
        raise FiscalValidationError(f"NF-e XML field {name} is blank")
    if len(value) > max_length:
        raise FiscalValidationError(f"NF-e XML field {name} is too long")
    return value


def _decimal(parent: ElementTree.Element, name: str) -> Decimal:
    raw = _text(parent, name, max_length=64)
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise FiscalValidationError(f"NF-e XML field {name} is invalid") from exc
    if not value.is_finite():
        raise FiscalValidationError(f"NF-e XML field {name} is invalid")
    return value


def parse_nfe_xml(
    *,
    scope: ExecutionScope,
    recipient_document: Cnpj,
    xml_content: bytes,
    source: FiscalInboundSource,
    discovered_at: datetime,
    nsu: str | None = None,
) -> FiscalInboundDocument:
    """Parse authoritative XML without provider-specific or host-specific behavior."""

    if not isinstance(xml_content, bytes) or not xml_content:
        raise FiscalValidationError("xml_content must be non-empty bytes")
    if len(xml_content) > _MAX_XML_BYTES:
        raise FiscalValidationError("xml_content exceeds 10 MiB")
    upper_content = xml_content.upper()
    if b"<!DOCTYPE" in upper_content or b"<!ENTITY" in upper_content:
        raise FiscalValidationError("NF-e XML declarations are not accepted")
    try:
        root = ElementTree.fromstring(xml_content)
    except ElementTree.ParseError as exc:
        raise FiscalValidationError("NF-e XML is malformed") from exc

    inf_nfe = _descendant(root, "infNFe")
    raw_id = (inf_nfe.attrib.get("Id") or "").strip()
    if not raw_id.startswith("NFe"):
        raise FiscalValidationError("NF-e XML infNFe Id is invalid")
    access_key = NfeAccessKey(raw_id[3:])
    if access_key.model is not ElectronicInvoiceModel.NFE:
        raise FiscalValidationError("inbound NF-e XML requires model 55")

    issuer = _child(inf_nfe, "emit")
    issuer_document = Cnpj(_text(issuer, "CNPJ", max_length=32))
    issuer_name = _text(issuer, "xNome", max_length=256)
    recipient = _child(inf_nfe, "dest")
    parsed_recipient = Cnpj(_text(recipient, "CNPJ", max_length=32))
    if parsed_recipient != recipient_document:
        raise FiscalValidationError("NF-e recipient differs from requested recipient")

    ide = _child(inf_nfe, "ide")
    issued_raw = _text(ide, "dhEmi", max_length=64)
    try:
        issued_at = datetime.fromisoformat(issued_raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FiscalValidationError("NF-e dhEmi is invalid") from exc

    items: list[FiscalInboundItem] = []
    for det in (node for node in inf_nfe if _local_name(node.tag) == "det"):
        raw_line = (det.attrib.get("nItem") or "").strip()
        if not raw_line.isdigit():
            raise FiscalValidationError("NF-e det nItem is invalid")
        product = _child(det, "prod")
        items.append(
            FiscalInboundItem(
                line_number=int(raw_line),
                product_code=_text(product, "cProd", max_length=128),
                description=_text(product, "xProd", max_length=512),
                ncm=_text(product, "NCM", max_length=8),
                commercial_unit=_text(product, "uCom", max_length=16),
                quantity=_decimal(product, "qCom"),
                unit_value=_decimal(product, "vUnCom"),
                total_value=_decimal(product, "vProd"),
            )
        )

    return FiscalInboundDocument(
        scope=scope,
        access_key=access_key,
        recipient_document=parsed_recipient,
        issuer_document=issuer_document,
        issuer_name=issuer_name,
        issued_at=issued_at,
        status=FiscalInboundStatus.DETECTED,
        source=source,
        xml_content=xml_content,
        items=tuple(items),
        discovered_at=discovered_at,
        nsu=nsu,
    )
