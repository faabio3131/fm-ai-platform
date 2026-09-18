"""Fail-closed jurisdiction capability matrix for Brazilian fiscal operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from kordena_fiscal.domain import (
    BrazilianJurisdiction,
    FiscalDocumentKind,
    FiscalDomainError,
    FiscalEnvironment,
    FiscalValidationError,
)

from .rtc import TechnicalValidationMode


class JurisdictionCapabilityError(FiscalDomainError):
    """Raised when jurisdiction capability cannot be established safely."""


class FiscalCapabilityLevel(IntEnum):
    """Technical readiness level; never implies legal homologation unless explicit."""

    CONTRACT_ONLY = 1
    HOMOLOGATION_READY = 2
    PRODUCTION_APPROVED = 3


def _required(value: str, field_name: str, max_length: int = 256) -> str:
    normalized = value.strip()
    if not normalized:
        raise FiscalValidationError(f"{field_name} must not be blank")
    if len(normalized) > max_length:
        raise FiscalValidationError(f"{field_name} exceeds max length {max_length}")
    return normalized


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FiscalValidationError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class JurisdictionCapabilityRule:
    """Explicit support statement for one document family and jurisdiction."""

    rule_id: str
    version: int
    state_code: str
    document_kind: FiscalDocumentKind
    environment: FiscalEnvironment
    capability_level: FiscalCapabilityLevel
    validation_mode: TechnicalValidationMode
    effective_from: datetime
    source_normative: str
    municipality_ibge_code: str | None = None
    effective_to: datetime | None = None
    priority: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _required(self.rule_id, "rule_id", 128))
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise FiscalValidationError("rule version must be an integer >= 1")
        jurisdiction = BrazilianJurisdiction(self.state_code, self.municipality_ibge_code)
        object.__setattr__(self, "state_code", jurisdiction.state_code)
        object.__setattr__(
            self,
            "municipality_ibge_code",
            jurisdiction.municipality_ibge_code,
        )
        if not isinstance(self.document_kind, FiscalDocumentKind):
            raise FiscalValidationError("document_kind must be FiscalDocumentKind")
        if not isinstance(self.environment, FiscalEnvironment):
            raise FiscalValidationError("environment must be FiscalEnvironment")
        if not isinstance(self.capability_level, FiscalCapabilityLevel):
            raise FiscalValidationError("capability_level must be FiscalCapabilityLevel")
        if not isinstance(self.validation_mode, TechnicalValidationMode):
            raise FiscalValidationError("validation_mode must be TechnicalValidationMode")
        _aware(self.effective_from, "effective_from")
        if self.effective_to is not None:
            _aware(self.effective_to, "effective_to")
            if self.effective_to <= self.effective_from:
                raise FiscalValidationError("effective_to must be after effective_from")
        object.__setattr__(
            self,
            "source_normative",
            _required(self.source_normative, "source_normative", 1000),
        )
        if (
            not isinstance(self.priority, int)
            or isinstance(self.priority, bool)
            or self.priority < 0
        ):
            raise FiscalValidationError("priority must be an integer >= 0")

    def matches(
        self,
        *,
        jurisdiction: BrazilianJurisdiction,
        document_kind: FiscalDocumentKind,
        environment: FiscalEnvironment,
        instant: datetime,
    ) -> bool:
        _aware(instant, "instant")
        if self.state_code != jurisdiction.state_code:
            return False
        if self.municipality_ibge_code is not None:
            if self.municipality_ibge_code != jurisdiction.municipality_ibge_code:
                return False
        if self.document_kind is not document_kind:
            return False
        if self.environment is not environment:
            return False
        if instant < self.effective_from:
            return False
        return self.effective_to is None or instant < self.effective_to

    @property
    def rank(self) -> tuple[int, int]:
        return (1 if self.municipality_ibge_code is not None else 0, self.priority)


class JurisdictionCapabilityMatrix:
    """Resolve jurisdiction support without implicit national fallback."""

    def __init__(self, rules: tuple[JurisdictionCapabilityRule, ...]) -> None:
        if not rules or not all(isinstance(rule, JurisdictionCapabilityRule) for rule in rules):
            raise FiscalValidationError(
                "rules must contain at least one JurisdictionCapabilityRule"
            )
        identities = [(rule.rule_id, rule.version) for rule in rules]
        if len(identities) != len(set(identities)):
            raise FiscalValidationError("jurisdiction rules must have unique id/version")
        self._rules = rules

    def resolve(
        self,
        *,
        jurisdiction: BrazilianJurisdiction,
        document_kind: FiscalDocumentKind,
        environment: FiscalEnvironment,
        instant: datetime,
        minimum_level: FiscalCapabilityLevel = FiscalCapabilityLevel.CONTRACT_ONLY,
    ) -> JurisdictionCapabilityRule:
        if not isinstance(jurisdiction, BrazilianJurisdiction):
            raise FiscalValidationError("jurisdiction must be BrazilianJurisdiction")
        if not isinstance(document_kind, FiscalDocumentKind):
            raise FiscalValidationError("document_kind must be FiscalDocumentKind")
        if not isinstance(environment, FiscalEnvironment):
            raise FiscalValidationError("environment must be FiscalEnvironment")
        if not isinstance(minimum_level, FiscalCapabilityLevel):
            raise FiscalValidationError("minimum_level must be FiscalCapabilityLevel")
        _aware(instant, "instant")

        matches = [
            rule
            for rule in self._rules
            if rule.matches(
                jurisdiction=jurisdiction,
                document_kind=document_kind,
                environment=environment,
                instant=instant,
            )
        ]
        if not matches:
            raise JurisdictionCapabilityError(
                "no explicit jurisdiction capability rule matches fiscal context"
            )
        best_rank = max(rule.rank for rule in matches)
        winners = [rule for rule in matches if rule.rank == best_rank]
        if len(winners) != 1:
            raise JurisdictionCapabilityError("ambiguous jurisdiction capability resolution")
        selected = winners[0]
        if selected.capability_level < minimum_level:
            raise JurisdictionCapabilityError(
                "jurisdiction capability is below the required readiness level"
            )
        return selected
