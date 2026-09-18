"""Issuer fiscal profile value objects and snapshot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from .errors import FiscalValidationError
from .identifiers import CnaeCode, Cnpj
from .primitives import BrazilianJurisdiction, ExecutionScope, _required_text

_REGISTRATION_NON_ALNUM = re.compile(r"[^0-9A-Z]")
_POSTAL_CODE_NON_DIGITS = re.compile(r"\D")


class TaxRegimeCode(IntEnum):
    """NF-e/NFC-e Código de Regime Tributário (CRT)."""

    SIMPLES_NACIONAL = 1
    SIMPLES_NACIONAL_EXCESS_SUBLIMIT = 2
    NORMAL = 3
    MEI = 4


@dataclass(frozen=True, slots=True)
class StateRegistration:
    """State registration with explicit exemption semantics.

    State-specific digit algorithms remain outside this generic value object and
    will be introduced through jurisdiction-aware validation rules later.
    """

    state_code: str
    number: str | None = None
    exempt: bool = False

    def __post_init__(self) -> None:
        jurisdiction = BrazilianJurisdiction(self.state_code)
        object.__setattr__(self, "state_code", jurisdiction.state_code)

        if self.exempt:
            if self.number not in (None, ""):
                raise FiscalValidationError(
                    "state registration number must be absent when exempt is true"
                )
            object.__setattr__(self, "number", None)
            return

        if self.number is None:
            raise FiscalValidationError(
                "state registration number is required when issuer is not exempt"
            )

        normalized = _REGISTRATION_NON_ALNUM.sub("", self.number.upper())
        if not normalized:
            raise FiscalValidationError("state registration number must not be blank")
        if len(normalized) > 32:
            raise FiscalValidationError("state registration number exceeds max length 32")
        object.__setattr__(self, "number", normalized)


@dataclass(frozen=True, slots=True)
class MunicipalRegistration:
    """Municipal registration kept generic because validation varies by municipality."""

    number: str

    def __post_init__(self) -> None:
        normalized = _REGISTRATION_NON_ALNUM.sub("", self.number.upper())
        if not normalized:
            raise FiscalValidationError("municipal registration number must not be blank")
        if len(normalized) > 32:
            raise FiscalValidationError("municipal registration number exceeds max length 32")
        object.__setattr__(self, "number", normalized)


@dataclass(frozen=True, slots=True)
class FiscalAddress:
    """Brazilian issuer address required by fiscal document generation."""

    street: str
    number: str
    district: str
    municipality_name: str
    jurisdiction: BrazilianJurisdiction
    postal_code: str
    complement: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "street", _required_text(self.street, "street", max_length=120))
        object.__setattr__(self, "number", _required_text(self.number, "number", max_length=60))
        object.__setattr__(
            self,
            "district",
            _required_text(self.district, "district", max_length=60),
        )
        object.__setattr__(
            self,
            "municipality_name",
            _required_text(self.municipality_name, "municipality_name", max_length=60),
        )
        if not isinstance(self.jurisdiction, BrazilianJurisdiction):
            raise FiscalValidationError("jurisdiction must be a BrazilianJurisdiction")
        if self.jurisdiction.municipality_ibge_code is None:
            raise FiscalValidationError(
                "issuer fiscal address requires municipality_ibge_code"
            )

        postal_code = _POSTAL_CODE_NON_DIGITS.sub("", self.postal_code)
        if len(postal_code) != 8:
            raise FiscalValidationError("postal_code must contain exactly 8 digits")
        object.__setattr__(self, "postal_code", postal_code)

        if self.complement is not None:
            complement = self.complement.strip()
            if len(complement) > 60:
                raise FiscalValidationError("complement exceeds max length 60")
            object.__setattr__(self, "complement", complement or None)


@dataclass(frozen=True, slots=True)
class FiscalProfile:
    """Immutable, versioned issuer profile for one host execution scope."""

    profile_id: str
    scope: ExecutionScope
    cnpj: Cnpj
    legal_name: str
    tax_regime: TaxRegimeCode
    state_registration: StateRegistration
    primary_cnae: CnaeCode
    address: FiscalAddress
    effective_from: datetime
    version: int = 1
    trade_name: str | None = None
    municipal_registration: MunicipalRegistration | None = None
    effective_to: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _required_text(self.profile_id, "profile_id", max_length=128),
        )
        if not isinstance(self.scope, ExecutionScope):
            raise FiscalValidationError("scope must be an ExecutionScope")
        if not isinstance(self.cnpj, Cnpj):
            raise FiscalValidationError("cnpj must be a Cnpj")
        object.__setattr__(
            self,
            "legal_name",
            _required_text(self.legal_name, "legal_name", max_length=120),
        )
        if not isinstance(self.tax_regime, TaxRegimeCode):
            raise FiscalValidationError("tax_regime must be a TaxRegimeCode")
        if not isinstance(self.state_registration, StateRegistration):
            raise FiscalValidationError(
                "state_registration must be a StateRegistration"
            )
        if not isinstance(self.primary_cnae, CnaeCode):
            raise FiscalValidationError("primary_cnae must be a CnaeCode")
        if not isinstance(self.address, FiscalAddress):
            raise FiscalValidationError("address must be a FiscalAddress")
        if self.state_registration.state_code != self.address.jurisdiction.state_code:
            raise FiscalValidationError(
                "state registration and fiscal address must belong to the same state"
            )

        if self.trade_name is not None:
            trade_name = self.trade_name.strip()
            if len(trade_name) > 120:
                raise FiscalValidationError("trade_name exceeds max length 120")
            object.__setattr__(self, "trade_name", trade_name or None)

        if self.municipal_registration is not None and not isinstance(
            self.municipal_registration, MunicipalRegistration
        ):
            raise FiscalValidationError(
                "municipal_registration must be a MunicipalRegistration"
            )

        if self.effective_from.tzinfo is None or self.effective_from.utcoffset() is None:
            raise FiscalValidationError("effective_from must be timezone-aware")
        if self.effective_to is not None:
            if self.effective_to.tzinfo is None or self.effective_to.utcoffset() is None:
                raise FiscalValidationError("effective_to must be timezone-aware")
            if self.effective_to <= self.effective_from:
                raise FiscalValidationError("effective_to must be after effective_from")
        if self.version < 1:
            raise FiscalValidationError("version must be >= 1")

    @property
    def snapshot_key(self) -> tuple[str, int]:
        return (self.profile_id, self.version)

    def is_effective_at(self, instant: datetime) -> bool:
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise FiscalValidationError("instant must be timezone-aware")
        if instant < self.effective_from:
            return False
        return self.effective_to is None or instant < self.effective_to
