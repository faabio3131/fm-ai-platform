"""Public tax-rule engine surface."""

from .engine import TaxRuleAmbiguityError, TaxRuleEngine, TaxRuleNotFoundError
from .models import (
    RecipientTaxProfile,
    TaxDecision,
    TaxOperationType,
    TaxRule,
    TaxRuleContext,
    TaxRuleOutcome,
    TaxRuleSelector,
)
from .restaurant import (
    CorporateMealContractFacts,
    RestaurantBaseAdjustmentDecision,
    RestaurantBaseAdjustmentFacts,
    RestaurantEstablishmentKind,
    RestaurantSupplyDecision,
    RestaurantSupplyFacts,
    RestaurantSupplyKind,
    RestaurantTaxClassifier,
    RestaurantTaxTreatment,
)

__all__ = [
    "CorporateMealContractFacts",
    "RecipientTaxProfile",
    "RestaurantBaseAdjustmentDecision",
    "RestaurantBaseAdjustmentFacts",
    "RestaurantEstablishmentKind",
    "RestaurantSupplyDecision",
    "RestaurantSupplyFacts",
    "RestaurantSupplyKind",
    "RestaurantTaxClassifier",
    "RestaurantTaxTreatment",
    "TaxDecision",
    "TaxOperationType",
    "TaxRule",
    "TaxRuleAmbiguityError",
    "TaxRuleContext",
    "TaxRuleEngine",
    "TaxRuleNotFoundError",
    "TaxRuleOutcome",
    "TaxRuleSelector",
]
