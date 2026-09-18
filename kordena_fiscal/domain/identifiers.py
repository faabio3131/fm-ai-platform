"""Brazilian fiscal identifiers used by issuer profiles."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import FiscalValidationError

_CNPJ_MASK_CHARS = re.compile(r"[.\-/\s]")
_CNPJ_PATTERN = re.compile(r"^[0-9A-Z]{12}[0-9]{2}$")
_CNAE_NON_DIGITS = re.compile(r"\D")


def _cnpj_check_digit(characters: str, weights: tuple[int, ...]) -> int:
    total = sum(
        (ord(character) - 48) * weight
        for character, weight in zip(characters, weights, strict=True)
    )
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def _calculate_cnpj_dv(base: str) -> str:
    first_weights = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    first = _cnpj_check_digit(base, first_weights)
    second_weights = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
    second = _cnpj_check_digit(f"{base}{first}", second_weights)
    return f"{first}{second}"


@dataclass(frozen=True, slots=True)
class Cnpj:
    """CNPJ value object supporting numeric and alphanumeric formats.

    The first twelve positions may contain digits or uppercase letters. The final
    two positions remain numeric check digits calculated with modulo 11.
    """

    value: str

    def __post_init__(self) -> None:
        normalized = _CNPJ_MASK_CHARS.sub("", self.value).upper()
        if not _CNPJ_PATTERN.fullmatch(normalized):
            raise FiscalValidationError(
                "CNPJ must have 12 alphanumeric positions followed by 2 numeric check digits"
            )
        if normalized == "0" * 14:
            raise FiscalValidationError("CNPJ all-zero value is not valid")
        expected_dv = _calculate_cnpj_dv(normalized[:12])
        if normalized[-2:] != expected_dv:
            raise FiscalValidationError("CNPJ check digits are invalid")
        object.__setattr__(self, "value", normalized)

    @property
    def formatted(self) -> str:
        value = self.value
        return f"{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}"


@dataclass(frozen=True, slots=True)
class CnaeCode:
    """Seven-digit CNAE subclass code, stored without presentation punctuation."""

    value: str

    def __post_init__(self) -> None:
        normalized = _CNAE_NON_DIGITS.sub("", self.value)
        if len(normalized) != 7:
            raise FiscalValidationError("CNAE code must contain exactly 7 digits")
        object.__setattr__(self, "value", normalized)

    @property
    def formatted(self) -> str:
        value = self.value
        return f"{value[:4]}-{value[4]}/{value[5:]}"
