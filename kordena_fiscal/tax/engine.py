"""Deterministic resolver for versioned fiscal tax rules."""

from __future__ import annotations

from collections.abc import Iterable

from kordena_fiscal.domain import FiscalDomainError

from .models import TaxDecision, TaxRule, TaxRuleContext


class TaxRuleNotFoundError(FiscalDomainError):
    """Raised when no effective rule matches a tax context."""


class TaxRuleAmbiguityError(FiscalDomainError):
    """Raised when multiple matching rules have the same winning rank."""


class TaxRuleEngine:
    """Resolve one explainable decision from effective versioned rules."""

    def resolve(
        self,
        context: TaxRuleContext,
        rules: Iterable[TaxRule],
    ) -> TaxDecision:
        matches = [rule for rule in rules if rule.matches(context)]
        if not matches:
            raise TaxRuleNotFoundError("no effective tax rule matched the supplied context")

        ordered = sorted(matches, key=lambda rule: rule.rank, reverse=True)
        winner = ordered[0]
        tied = [rule for rule in ordered if rule.rank == winner.rank]
        if len(tied) > 1:
            identities = ", ".join(
                sorted(f"{rule.rule_id}@v{rule.version}" for rule in tied)
            )
            raise TaxRuleAmbiguityError(
                f"ambiguous tax rules at rank {winner.rank}: {identities}"
            )

        return TaxDecision(
            rule_id=winner.rule_id,
            rule_version=winner.version,
            source_normative=winner.source_normative,
            outcome=winner.outcome,
            rank=winner.rank,
        )
