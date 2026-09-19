"""Restaurant-specific IBS/CBS classification primitives.

The rules in this module are intentionally narrow and traceable to the current
specific regime for bars, restaurants and similar establishments. Final monetary
tax calculation remains outside this classifier.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from kordena_fiscal.domain import FiscalValidationError, Money


class RestaurantEstablishmentKind(StrEnum):
    BAR_RESTAURANT = "bar_restaurant"
    SNACK_BAR = "snack_bar"
    PASTRY_SHOP = "pastry_shop"
    BAKERY = "bakery"
    TEA_HOUSE = "tea_house"
    JUICE_HOUSE = "juice_house"
    SWEET_SAVORY_HOUSE = "sweet_savory_house"
    COFFEE_SHOP = "coffee_shop"
    ICE_CREAM_SHOP = "ice_cream_shop"
    SIMILAR = "similar"


class RestaurantSupplyKind(StrEnum):
    FOOD = "food"
    NON_ALCOHOLIC_BEVERAGE = "non_alcoholic_beverage"
    ALCOHOLIC_BEVERAGE = "alcoholic_beverage"
    OTHER = "other"


class RestaurantTaxTreatment(StrEnum):
    SPECIFIC_REGIME = "specific_regime"
    GENERAL_REGIME = "general_regime"


@dataclass(frozen=True, slots=True)
class CorporateMealContractFacts:
    """Facts needed for the contracted-corporate-meal exclusion."""

    recipient_is_legal_entity: bool = False
    under_contract: bool = False
    matches_excluded_nbs_or_provider_cnae: bool = False

    @property
    def exclusion_applies(self) -> bool:
        return (
            self.recipient_is_legal_entity
            and self.under_contract
            and self.matches_excluded_nbs_or_provider_cnae
        )


@dataclass(frozen=True, slots=True)
class RestaurantSupplyFacts:
    """Legally relevant facts for one restaurant supply line."""

    establishment_kind: RestaurantEstablishmentKind
    supply_kind: RestaurantSupplyKind
    prepared_or_manipulated_on_premises: bool
    acquired_from_third_party: bool = False
    industrialized_non_alcoholic_beverage: bool = False
    corporate_meal: CorporateMealContractFacts = CorporateMealContractFacts()

    def __post_init__(self) -> None:
        if not isinstance(self.establishment_kind, RestaurantEstablishmentKind):
            raise FiscalValidationError(
                "establishment_kind must be a RestaurantEstablishmentKind"
            )
        if not isinstance(self.supply_kind, RestaurantSupplyKind):
            raise FiscalValidationError("supply_kind must be a RestaurantSupplyKind")
        if not isinstance(self.corporate_meal, CorporateMealContractFacts):
            raise FiscalValidationError(
                "corporate_meal must be CorporateMealContractFacts"
            )
        if (
            self.industrialized_non_alcoholic_beverage
            and self.supply_kind is not RestaurantSupplyKind.NON_ALCOHOLIC_BEVERAGE
        ):
            raise FiscalValidationError(
                "industrialized_non_alcoholic_beverage requires non-alcoholic supply kind"
            )


@dataclass(frozen=True, slots=True)
class RestaurantSupplyDecision:
    """Explainable classification of one supply under the restaurant regime."""

    treatment: RestaurantTaxTreatment
    reason_code: str
    normative_references: tuple[str, ...]
    rate_reduction_percent: Decimal | None
    recipient_credit_allowed: bool | None

    @property
    def is_specific_regime(self) -> bool:
        return self.treatment is RestaurantTaxTreatment.SPECIFIC_REGIME


@dataclass(frozen=True, slots=True)
class RestaurantBaseAdjustmentFacts:
    """Operation-level facts relevant to gratuity/platform base exclusions.

    Amounts are kept separate from eligibility. The downstream calculation layer
    will apply the legally required allocation to mixed operations.
    """

    total_operation_amount: Money
    food_beverage_supply_amount: Money
    specific_regime_supply_amount: Money
    gratuity_amount: Money = Money.zero()
    gratuity_fully_passed_to_employees: bool = False
    gratuity_segregated_in_fiscal_document: bool = False
    platform_amount_not_passed_to_establishment: Money = Money.zero()
    platform_amount_segregated_in_fiscal_document: bool = False
    specific_and_general_values_segregated: bool = True

    def __post_init__(self) -> None:
        monetary_values = (
            self.total_operation_amount,
            self.food_beverage_supply_amount,
            self.specific_regime_supply_amount,
            self.gratuity_amount,
            self.platform_amount_not_passed_to_establishment,
        )
        if not all(isinstance(value, Money) for value in monetary_values):
            raise FiscalValidationError("restaurant operation amounts must be Money")
        if any(value.amount < 0 for value in monetary_values):
            raise FiscalValidationError("restaurant operation amounts must be non-negative")
        if self.total_operation_amount.amount <= 0:
            raise FiscalValidationError("total_operation_amount must be greater than zero")
        if self.food_beverage_supply_amount.amount > self.total_operation_amount.amount:
            raise FiscalValidationError(
                "food_beverage_supply_amount cannot exceed total_operation_amount"
            )
        if self.specific_regime_supply_amount.amount > self.food_beverage_supply_amount.amount:
            raise FiscalValidationError(
                "specific_regime_supply_amount cannot exceed food_beverage_supply_amount"
            )


@dataclass(frozen=True, slots=True)
class RestaurantBaseAdjustmentDecision:
    """Eligibility result for base exclusions and document segregation."""

    specific_regime_documentation_valid: bool
    gratuity_exclusion_eligible: bool
    platform_exclusion_eligible: bool
    specific_supply_ratio: Decimal
    normative_references: tuple[str, ...]
    reasons: tuple[str, ...]


class RestaurantTaxClassifier:
    """Classify supplies and operation adjustments for the specific regime."""

    _SPECIFIC_REFS = (
        "LC 214/2025 arts. 273-276 (texto atualizado)",
        "Decreto 12.955/2026 arts. 396-401",
    )

    def classify_supply(self, facts: RestaurantSupplyFacts) -> RestaurantSupplyDecision:
        if not isinstance(facts, RestaurantSupplyFacts):
            raise FiscalValidationError("facts must be RestaurantSupplyFacts")

        if facts.corporate_meal.exclusion_applies:
            return self._general("contracted_corporate_meal_excluded")

        if facts.supply_kind is RestaurantSupplyKind.ALCOHOLIC_BEVERAGE:
            return self._general("alcoholic_beverage_excluded")

        if facts.supply_kind is RestaurantSupplyKind.OTHER:
            return self._general("supply_kind_outside_restaurant_specific_regime")

        if facts.industrialized_non_alcoholic_beverage:
            return self._general("industrialized_non_alcoholic_beverage_excluded")

        if facts.acquired_from_third_party and not facts.prepared_or_manipulated_on_premises:
            return self._general("third_party_non_prepared_supply_excluded")

        if not facts.prepared_or_manipulated_on_premises:
            return self._general("not_prepared_or_manipulated_on_premises")

        return RestaurantSupplyDecision(
            treatment=RestaurantTaxTreatment.SPECIFIC_REGIME,
            reason_code="prepared_food_or_non_alcoholic_beverage_in_specific_regime",
            normative_references=self._SPECIFIC_REFS,
            rate_reduction_percent=Decimal("40"),
            recipient_credit_allowed=False,
        )

    def evaluate_base_adjustments(
        self,
        facts: RestaurantBaseAdjustmentFacts,
    ) -> RestaurantBaseAdjustmentDecision:
        if not isinstance(facts, RestaurantBaseAdjustmentFacts):
            raise FiscalValidationError("facts must be RestaurantBaseAdjustmentFacts")

        reasons: list[str] = []
        documentation_valid = facts.specific_and_general_values_segregated
        if not documentation_valid:
            reasons.append("specific_and_general_values_not_segregated")

        food_beverage = facts.food_beverage_supply_amount.amount
        gratuity = facts.gratuity_amount.amount
        gratuity_within_limit = (
            food_beverage > 0 and gratuity <= food_beverage * Decimal("0.15")
        )
        gratuity_eligible = (
            documentation_valid
            and gratuity > 0
            and facts.gratuity_fully_passed_to_employees
            and facts.gratuity_segregated_in_fiscal_document
            and gratuity_within_limit
        )
        if gratuity > 0 and not gratuity_eligible:
            if not facts.gratuity_fully_passed_to_employees:
                reasons.append("gratuity_not_fully_passed_to_employees")
            if not facts.gratuity_segregated_in_fiscal_document:
                reasons.append("gratuity_not_segregated_in_fiscal_document")
            if not gratuity_within_limit:
                reasons.append("gratuity_exceeds_fifteen_percent_limit")

        platform_amount = facts.platform_amount_not_passed_to_establishment.amount
        platform_eligible = (
            documentation_valid
            and platform_amount > 0
            and facts.platform_amount_segregated_in_fiscal_document
        )
        if platform_amount > 0 and not platform_eligible:
            if not facts.platform_amount_segregated_in_fiscal_document:
                reasons.append("platform_amount_not_segregated_in_fiscal_document")

        ratio = (
            facts.specific_regime_supply_amount.amount
            / facts.total_operation_amount.amount
        )

        return RestaurantBaseAdjustmentDecision(
            specific_regime_documentation_valid=documentation_valid,
            gratuity_exclusion_eligible=gratuity_eligible,
            platform_exclusion_eligible=platform_eligible,
            specific_supply_ratio=ratio,
            normative_references=self._SPECIFIC_REFS,
            reasons=tuple(dict.fromkeys(reasons)),
        )

    def _general(self, reason_code: str) -> RestaurantSupplyDecision:
        return RestaurantSupplyDecision(
            treatment=RestaurantTaxTreatment.GENERAL_REGIME,
            reason_code=reason_code,
            normative_references=self._SPECIFIC_REFS,
            rate_reduction_percent=None,
            recipient_credit_allowed=None,
        )
