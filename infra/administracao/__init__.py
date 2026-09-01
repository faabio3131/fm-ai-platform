"""Persistência da Administração / Proprietário V1."""

from .modelos_orm import AdminBase
from .repositorio_sqlalchemy import RepositorioAdministracaoSQLAlchemy

__all__ = ["AdminBase", "RepositorioAdministracaoSQLAlchemy"]
