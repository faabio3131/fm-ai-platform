"""Strict AI adapter for preliminary fiscal evidence extraction."""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from PIL import Image, UnidentifiedImageError

from kordena_fiscal.domain import Cnpj, FiscalValidationError
from kordena_fiscal.intake import (
    FiscalIntakeArtifact,
    FiscalIntakeCandidateItem,
    FiscalIntakeExtraction,
    FiscalIntakeSource,
)
from kordena_fiscal.xml import NfeAccessKey

_PROMPT = """Extract fiscal evidence into one JSON object only.
This content is preliminary and must never override the official XML/DF-e.
Schema: {"access_key": string|null, "issuer_document": string|null,
"recipient_document": string|null, "confidence": number 0..1,
"items": [{"line_number": integer, "product_code": string|null,
"description": string, "ncm": string|null, "commercial_unit": string|null,
"quantity": number|null, "unit_value": number|null, "total_value": number|null}]}.
Do not infer missing identifiers. Return null for unreadable optional fields.
"""

_ROOT_FIELDS = {
    "access_key",
    "issuer_document",
    "recipient_document",
    "confidence",
    "items",
}
_ITEM_FIELDS = {
    "line_number",
    "product_code",
    "description",
    "ncm",
    "commercial_unit",
    "quantity",
    "unit_value",
    "total_value",
}


def _reject_unknown_fields(payload: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise FiscalValidationError(
            "extraction contains unknown fields: " + ", ".join(unknown)
        )


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise FiscalValidationError(f"{key} must be text or null")
    return value


def _decimal(value: Any, field: str, *, required: bool = False) -> Decimal | None:
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise FiscalValidationError(f"{field} must be numeric")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise FiscalValidationError(f"{field} must be numeric") from exc


def _json_object(text: str) -> Mapping[str, Any]:
    normalized = text.strip()
    if normalized.startswith("```") and normalized.endswith("```"):
        lines = normalized.splitlines()
        if len(lines) < 3:
            raise FiscalValidationError("extraction response is not valid JSON")
        normalized = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise FiscalValidationError("extraction response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise FiscalValidationError("extraction response must be one JSON object")
    return value


def parse_fiscal_intake_extraction(text: str) -> FiscalIntakeExtraction:
    if not isinstance(text, str):
        raise FiscalValidationError("extraction response must be text")
    payload = _json_object(text)
    _reject_unknown_fields(payload, _ROOT_FIELDS)
    if "confidence" not in payload or "items" not in payload:
        raise FiscalValidationError("extraction requires confidence and items")
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        raise FiscalValidationError("items must be a JSON array")

    items: list[FiscalIntakeCandidateItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise FiscalValidationError("each item must be a JSON object")
        _reject_unknown_fields(raw_item, _ITEM_FIELDS)
        line_number = raw_item.get("line_number")
        if not isinstance(line_number, int) or isinstance(line_number, bool):
            raise FiscalValidationError("line_number must be an integer")
        description = raw_item.get("description")
        if not isinstance(description, str):
            raise FiscalValidationError("description must be text")
        items.append(
            FiscalIntakeCandidateItem(
                line_number=line_number,
                product_code=_optional_text(raw_item, "product_code"),
                description=description,
                ncm=_optional_text(raw_item, "ncm"),
                commercial_unit=_optional_text(raw_item, "commercial_unit"),
                quantity=_decimal(raw_item.get("quantity"), "quantity"),
                unit_value=_decimal(raw_item.get("unit_value"), "unit_value"),
                total_value=_decimal(raw_item.get("total_value"), "total_value"),
            )
        )

    access_key = _optional_text(payload, "access_key")
    issuer = _optional_text(payload, "issuer_document")
    recipient = _optional_text(payload, "recipient_document")
    confidence = _decimal(payload.get("confidence"), "confidence", required=True)
    if confidence is None:  # pragma: no cover - guarded by required=True
        raise FiscalValidationError("confidence is required")
    return FiscalIntakeExtraction(
        items=tuple(items),
        confidence=confidence,
        access_key=None if access_key is None else NfeAccessKey(access_key),
        issuer_document=None if issuer is None else Cnpj(issuer),
        recipient_document=None if recipient is None else Cnpj(recipient),
    )


class GeminiFiscalIntakeExtractor:
    """Provider-boundary adapter with local media and output validation."""

    def __init__(self, generate_content: Callable[..., Any]) -> None:
        self._generate_content = generate_content

    @staticmethod
    def _provider_part(artifact: FiscalIntakeArtifact) -> Any:
        if artifact.source is FiscalIntakeSource.PDF:
            if not artifact.content.startswith(b"%PDF-"):
                raise FiscalValidationError("PDF content has an invalid signature")
            return {"mime_type": artifact.media_type, "data": artifact.content}

        try:
            with Image.open(io.BytesIO(artifact.content)) as image:
                image.load()
                detected = image.format
        except (UnidentifiedImageError, OSError) as exc:
            raise FiscalValidationError("image content is invalid") from exc
        expected = {"image/jpeg": "JPEG", "image/png": "PNG"}[artifact.media_type]
        if detected != expected:
            raise FiscalValidationError("image content differs from declared media type")
        return Image.open(io.BytesIO(artifact.content))

    def extract(self, artifact: FiscalIntakeArtifact) -> FiscalIntakeExtraction:
        response = self._generate_content(
            contents=[_PROMPT, self._provider_part(artifact)]
        )
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            raise FiscalValidationError("provider response has no textual JSON")
        return parse_fiscal_intake_extraction(text)
