"""Domain exceptions for the fiscal engine."""


class FiscalDomainError(Exception):
    """Base exception for deterministic fiscal-domain failures."""


class FiscalValidationError(FiscalDomainError, ValueError):
    """Raised when a fiscal value object violates a domain invariant."""
