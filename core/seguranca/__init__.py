"""Fundação de tenant, autenticação, RBAC, alçadas, segredos e auditoria."""

from .autenticacao import (
    IdentidadeUsuario,
    RepositorioIdentidades,
    ServicoAutenticacao,
    hash_password,
    verify_password,
)
from .autorizacao import AutorizarAcao, DecisaoAutorizacao, recurso_no_escopo
from .contexto import ContextoExecucao
from .permissoes import MATRIZ_PADRAO, Papel, Permissao
from .segredos import ReferenceSecretStore, SecretStore, SecretValue, env_reference

__all__ = [
    "MATRIZ_PADRAO",
    "AutorizarAcao",
    "ContextoExecucao",
    "DecisaoAutorizacao",
    "IdentidadeUsuario",
    "Papel",
    "Permissao",
    "ReferenceSecretStore",
    "RepositorioIdentidades",
    "SecretStore",
    "SecretValue",
    "ServicoAutenticacao",
    "env_reference",
    "hash_password",
    "recurso_no_escopo",
    "verify_password",
]
