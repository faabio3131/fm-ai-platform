"""Canonical inbound fiscal contracts for Fiscal V1."""

from .models import (
    DfeDistributionBatch,
    DfeDistributionEntry,
    FiscalInboundDocument,
    FiscalInboundItem,
    FiscalInboundSource,
    FiscalInboundStatus,
    FiscalManifestation,
    FiscalManifestationType,
    FiscalNsuCheckpoint,
)
from .parser import parse_nfe_xml

__all__ = [
    "DfeDistributionBatch",
    "DfeDistributionEntry",
    "FiscalInboundDocument",
    "FiscalInboundItem",
    "FiscalInboundSource",
    "FiscalInboundStatus",
    "FiscalManifestation",
    "FiscalManifestationType",
    "FiscalNsuCheckpoint",
    "parse_nfe_xml",
]
