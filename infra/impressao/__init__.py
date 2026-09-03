"""Infraestrutura comercial de impressão V1."""

from .adapter_tcp import ImpressoraTCPRaw
from .configuracao_sqlalchemy import ResolverDestinosImpressaoSQLAlchemy

__all__ = ["ImpressoraTCPRaw", "ResolverDestinosImpressaoSQLAlchemy"]
