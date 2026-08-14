"""Adapters SQLAlchemy para configurações externas."""

from .modelos_orm import IntegrationConfigBase, ServicoExternoConfigORM
from .repositorio_sqlalchemy import (
    ProntidaoCredenciaisSQLAlchemy,
    RepositorioConfiguracoesExternasSQLAlchemy,
)

__all__ = [
    "IntegrationConfigBase",
    "ProntidaoCredenciaisSQLAlchemy",
    "RepositorioConfiguracoesExternasSQLAlchemy",
    "ServicoExternoConfigORM",
]
