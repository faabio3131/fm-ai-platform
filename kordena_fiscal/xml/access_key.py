"""NF-e/NFC-e access-key construction with alphanumeric CNPJ support."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from kordena_fiscal.domain import Cnpj, ElectronicInvoiceModel, FiscalValidationError

_ACCESS_KEY_PATTERN = re.compile(r"^[0-9]{6}[A-Z0-9]{12}[0-9]{26}$")


@dataclass(frozen=True, slots=True)
class NfeAccessKey:
    """Validated 44-character NF-e/NFC-e access key."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not _ACCESS_KEY_PATTERN.fullmatch(normalized):
            raise FiscalValidationError(
                "access key must have 44 characters and match the CNPJ-alphanumeric layout"
            )
        if normalized[20:22] not in {"55", "65"}:
            raise FiscalValidationError("access key model must be NF-e 55 or NFC-e 65")
        body = normalized[:-1]
        expected = _calculate_access_key_dv(body)
        if normalized[-1] != str(expected):
            raise FiscalValidationError("access key check digit is invalid")
        object.__setattr__(self, "value", normalized)

    @property
    def issuer_identifier(self) -> str:
        return self.value[6:20]

    @property
    def model(self) -> ElectronicInvoiceModel:
        return ElectronicInvoiceModel(int(self.value[20:22]))

    @property
    def series(self) -> int:
        return int(self.value[22:25])

    @property
    def invoice_number(self) -> int:
        return int(self.value[25:34])


@dataclass(frozen=True, slots=True)
class AccessKeyInput:
    """Stable access-key fields for a CNPJ issuer."""

    state_ibge_code: str
    issued_at: datetime
    issuer_cnpj: Cnpj
    model: ElectronicInvoiceModel
    series: int
    invoice_number: int
    emission_type: int
    numeric_code: int

    def __post_init__(self) -> None:
        state_code = self.state_ibge_code.strip()
        if len(state_code) != 2 or not state_code.isdigit():
            raise FiscalValidationError("state_ibge_code must contain exactly 2 digits")
        object.__setattr__(self, "state_ibge_code", state_code)
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise FiscalValidationError("issued_at must be timezone-aware")
        if not isinstance(self.issuer_cnpj, Cnpj):
            raise FiscalValidationError("issuer_cnpj must be Cnpj")
        if not isinstance(self.model, ElectronicInvoiceModel):
            raise FiscalValidationError("model must be ElectronicInvoiceModel")
        _bounded_int(self.series, "series", 0, 999)
        _bounded_int(self.invoice_number, "invoice_number", 1, 999_999_999)
        _bounded_int(self.emission_type, "emission_type", 1, 9)
        _bounded_int(self.numeric_code, "numeric_code", 0, 99_999_999)


def build_access_key(data: AccessKeyInput) -> NfeAccessKey:
    """Build and validate a 44-character access key from canonical fields."""

    if not isinstance(data, AccessKeyInput):
        raise FiscalValidationError("data must be AccessKeyInput")
    year_month = f"{data.issued_at.year % 100:02d}{data.issued_at.month:02d}"
    body = "".join(
        (
            data.state_ibge_code,
            year_month,
            data.issuer_cnpj.value,
            f"{data.model.value:02d}",
            f"{data.series:03d}",
            f"{data.invoice_number:09d}",
            str(data.emission_type),
            f"{data.numeric_code:08d}",
        )
    )
    if len(body) != 43:
        raise FiscalValidationError("access key body must contain exactly 43 characters")
    return NfeAccessKey(f"{body}{_calculate_access_key_dv(body)}")


def _calculate_access_key_dv(body: str) -> int:
    if len(body) != 43:
        raise FiscalValidationError("access key body must contain exactly 43 characters")
    if not re.fullmatch(r"[0-9A-Z]{43}", body):
        raise FiscalValidationError("access key body contains unsupported characters")

    total = 0
    weight = 2
    for character in reversed(body):
        total += (ord(character) - 48) * weight
        weight = 2 if weight == 9 else weight + 1
    remainder = total % 11
    return 0 if remainder in {0, 1} else 11 - remainder


def _bounded_int(value: int, field_name: str, minimum: int, maximum: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise FiscalValidationError(f"{field_name} must be an integer")
    if value < minimum or value > maximum:
        raise FiscalValidationError(
            f"{field_name} must be between {minimum} and {maximum}"
        )
