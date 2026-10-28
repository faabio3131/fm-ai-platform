"""Public canonical domain surface for Kordena Fiscal Engine."""

from .errors import FiscalDomainError, FiscalValidationError
from .events import FiscalDomainEvent
from .identifiers import CnaeCode, Cnpj
from .primitives import (
    BrazilianJurisdiction,
    ElectronicInvoiceModel,
    ExecutionScope,
    FiscalDocumentKind,
    FiscalEnvironment,
    Money,
    SourceReference,
)
from .product import (
    CestCode,
    FiscalProductProfile,
    FiscalUnitCode,
    Gtin,
    NcmCode,
    ProductOrigin,
    TaxClassificationHints,
)
from .profile import (
    FiscalAddress,
    FiscalProfile,
    MunicipalRegistration,
    StateRegistration,
    TaxRegimeCode,
)

__all__ = [
    "BrazilianJurisdiction",
    "CestCode",
    "CnaeCode",
    "Cnpj",
    "ElectronicInvoiceModel",
    "ExecutionScope",
    "FiscalAddress",
    "FiscalDocumentKind",
    "FiscalDomainError",
    "FiscalDomainEvent",
    "FiscalEnvironment",
    "FiscalProductProfile",
    "FiscalProfile",
    "FiscalUnitCode",
    "FiscalValidationError",
    "Gtin",
    "Money",
    "MunicipalRegistration",
    "NcmCode",
    "ProductOrigin",
    "SourceReference",
    "StateRegistration",
    "TaxClassificationHints",
    "TaxRegimeCode",
]
