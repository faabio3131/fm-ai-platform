"""Versioned fiscal-product catalog primitives and snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from .errors import FiscalValidationError
from .primitives import ExecutionScope, _required_text

_DIGITS = re.compile(r"^\d+$")
_CEST_MASK_CHARS = re.compile(r"[.\-\s]")
_UNIT_PATTERN = re.compile(r"^[A-Z0-9]{1,6}$")
_CODE_PATTERN = re.compile(r"^[A-Z0-9._/-]+$")


@dataclass(frozen=True, slots=True)
class NcmCode:
    """Eight-digit Mercosur Common Nomenclature code for catalogued products."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().replace(".", "")
        if len(normalized) != 8 or not _DIGITS.fullmatch(normalized):
            raise FiscalValidationError("NCM code must contain exactly 8 digits")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class CestCode:
    """Seven-digit CEST code when substitution-tax classification requires one."""

    value: str

    def __post_init__(self) -> None:
        normalized = _CEST_MASK_CHARS.sub("", self.value.strip())
        if len(normalized) != 7 or not _DIGITS.fullmatch(normalized):
            raise FiscalValidationError("CEST code must contain exactly 7 digits")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class FiscalUnitCode:
    """Host-neutral commercial/taxable unit code used by fiscal documents."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not _UNIT_PATTERN.fullmatch(normalized):
            raise FiscalValidationError(
                "fiscal unit code must contain 1 to 6 uppercase alphanumeric characters"
            )
        object.__setattr__(self, "value", normalized)


class ProductOrigin(IntEnum):
    """ICMS product-origin codes used by NF-e/NFC-e item taxation."""

    NATIONAL = 0
    FOREIGN_DIRECT_IMPORT = 1
    FOREIGN_INTERNAL_MARKET = 2
    NATIONAL_IMPORT_CONTENT_ABOVE_40 = 3
    NATIONAL_BASIC_PROCESS = 4
    NATIONAL_IMPORT_CONTENT_AT_OR_BELOW_40 = 5
    FOREIGN_DIRECT_IMPORT_NO_NATIONAL_SIMILAR = 6
    FOREIGN_INTERNAL_MARKET_NO_NATIONAL_SIMILAR = 7
    NATIONAL_IMPORT_CONTENT_ABOVE_70 = 8


def _gtin_check_digit(payload: str) -> int:
    weighted = 0
    for index, character in enumerate(reversed(payload)):
        factor = 3 if index % 2 == 0 else 1
        weighted += int(character) * factor
    return (10 - (weighted % 10)) % 10


@dataclass(frozen=True, slots=True)
class Gtin:
    """GTIN-8/12/13/14 or the fiscal literal used when no GTIN exists."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if normalized == "SEM GTIN":
            object.__setattr__(self, "value", normalized)
            return
        if len(normalized) not in {8, 12, 13, 14} or not normalized.isdigit():
            raise FiscalValidationError(
                "GTIN must have 8, 12, 13 or 14 digits, or be the literal 'SEM GTIN'"
            )
        expected = _gtin_check_digit(normalized[:-1])
        if int(normalized[-1]) != expected:
            raise FiscalValidationError("GTIN check digit is invalid")
        object.__setattr__(self, "value", normalized)

    @property
    def is_absent(self) -> bool:
        return self.value == "SEM GTIN"


@dataclass(frozen=True, slots=True)
class TaxClassificationHints:
    """Optional catalog hints; the Tax Rule Engine remains final authority.

    These values are intentionally not CFOP/CST/CSOSN decisions because those can
    vary with operation, recipient, jurisdiction, regime and effective date.
    """

    fiscal_benefit_code: str | None = None
    ibs_cbs_classification_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "fiscal_benefit_code",
            self._normalize_optional_code(self.fiscal_benefit_code, "fiscal_benefit_code", 32),
        )
        object.__setattr__(
            self,
            "ibs_cbs_classification_code",
            self._normalize_optional_code(
                self.ibs_cbs_classification_code,
                "ibs_cbs_classification_code",
                32,
            ),
        )

    @staticmethod
    def _normalize_optional_code(value: str | None, field_name: str, max_length: int) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            return None
        if len(normalized) > max_length or not _CODE_PATTERN.fullmatch(normalized):
            raise FiscalValidationError(f"{field_name} has invalid format")
        return normalized


@dataclass(frozen=True, slots=True)
class FiscalProductProfile:
    """Immutable and effective-dated fiscal classification for one host product."""

    profile_id: str
    product_id: str
    scope: ExecutionScope
    commercial_code: str
    description: str
    ncm: NcmCode
    commercial_unit: FiscalUnitCode
    taxable_unit: FiscalUnitCode
    origin: ProductOrigin
    effective_from: datetime
    version: int = 1
    cest: CestCode | None = None
    gtin: Gtin | None = None
    hints: TaxClassificationHints = TaxClassificationHints()
    effective_to: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _required_text(self.profile_id, "profile_id", max_length=128),
        )
        object.__setattr__(
            self,
            "product_id",
            _required_text(self.product_id, "product_id", max_length=128),
        )
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be an ExecutionScope")
        object.__setattr__(
            self,
            "commercial_code",
            _required_text(self.commercial_code, "commercial_code", max_length=60),
        )
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, "description", max_length=120),
        )
        if not isinstance(self.ncm, NcmCode):
            raise FiscalValidationError("ncm must be an NcmCode")
        if not isinstance(self.commercial_unit, FiscalUnitCode):
            raise FiscalValidationError("commercial_unit must be a FiscalUnitCode")
        if not isinstance(self.taxable_unit, FiscalUnitCode):
            raise FiscalValidationError("taxable_unit must be a FiscalUnitCode")
        if not isinstance(self.origin, ProductOrigin):
            raise FiscalValidationError("origin must be a ProductOrigin")
        if self.cest is not None and not isinstance(self.cest, CestCode):
            raise FiscalValidationError("cest must be a CestCode when provided")
        if self.gtin is not None and not isinstance(self.gtin, Gtin):
            raise FiscalValidationError("gtin must be a Gtin when provided")
        if not isinstance(self.hints, TaxClassificationHints):
            raise FiscalValidationError("hints must be TaxClassificationHints")
        if self.version < 1:
            raise FiscalValidationError("version must be >= 1")
        if self.effective_from.tzinfo is None or self.effective_from.utcoffset() is None:
            raise FiscalValidationError("effective_from must be timezone-aware")
        if self.effective_to is not None:
            if self.effective_to.tzinfo is None or self.effective_to.utcoffset() is None:
                raise FiscalValidationError("effective_to must be timezone-aware")
            if self.effective_to <= self.effective_from:
                raise FiscalValidationError("effective_to must be after effective_from")

    def is_effective_at(self, instant: datetime) -> bool:
        """Return whether this immutable profile is valid at the supplied instant."""

        if instant.tzinfo is None or instant.utcoffset() is None:
            raise FiscalValidationError("instant must be timezone-aware")
        if instant < self.effective_from:
            return False
        return self.effective_to is None or instant < self.effective_to
