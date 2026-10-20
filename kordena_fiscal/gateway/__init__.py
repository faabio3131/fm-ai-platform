"""Provider-neutral fiscal authorization gateway surface."""

from .authorization import (
    AuthorizationRequest,
    AuthorizationResult,
    AuthorizationStatus,
    FiscalGateway,
    FiscalGatewayClient,
    GatewayContractError,
    GatewayProviderMetadata,
)
from .fake import FakeFiscalGateway, FakeGatewayMode

__all__ = [
    "AuthorizationRequest",
    "AuthorizationResult",
    "AuthorizationStatus",
    "FakeFiscalGateway",
    "FakeGatewayMode",
    "FiscalGateway",
    "FiscalGatewayClient",
    "GatewayContractError",
    "GatewayProviderMetadata",
]
