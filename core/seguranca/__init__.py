"""Fundacao pura de tenant, RBAC, alcadas, IDOR e auditoria."""

from .autorizacao import AutorizarAcao, DecisaoAutorizacao, recurso_no_escopo
from .contexto import ContextoExecucao
from .permissoes import MATRIZ_PADRAO, Papel, Permissao

__all__ = [
    "MATRIZ_PADRAO",
    "AutorizarAcao",
    "ContextoExecucao",
    "DecisaoAutorizacao",
    "Papel",
    "Permissao",
    "recurso_no_escopo",
]
