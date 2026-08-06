"""Portas e adapter in-memory para resolucao confiavel de escopo."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .erros import TenantNaoAutorizado, UnidadeNaoAutorizada


@dataclass(frozen=True)
class VinculoUsuarioTenant:
    usuario_id: str
    tenant_id: str
    valido_ate: datetime | None = None


@dataclass(frozen=True)
class VinculoUsuarioUnidade:
    usuario_id: str
    tenant_id: str
    unidade_id: str
    padrao: bool = False


class ResolvedorTenant(Protocol):
    def resolver(
        self, usuario_id: str, tenant_solicitado: str | None = None
    ) -> str: ...
    def disponiveis(self, usuario_id: str) -> frozenset[str]: ...


class ResolvedorUnidade(Protocol):
    def resolver(
        self, usuario_id: str, tenant_id: str, unidade_solicitada: str | None = None
    ) -> str: ...


class ResolvedorIdentidadeEmMemoria:
    def __init__(
        self,
        tenants: tuple[VinculoUsuarioTenant, ...],
        unidades: tuple[VinculoUsuarioUnidade, ...],
    ) -> None:
        self._tenants, self._unidades = tenants, unidades

    def disponiveis(self, usuario_id: str) -> frozenset[str]:
        return frozenset(
            v.tenant_id for v in self._tenants if v.usuario_id == usuario_id
        )

    def resolver(self, usuario_id: str, tenant_solicitado: str | None = None) -> str:
        permitidos = self.disponiveis(usuario_id)
        if not permitidos or tenant_solicitado not in permitidos:
            raise TenantNaoAutorizado("Recurso indisponivel")
        return tenant_solicitado

    def resolver_unidade(
        self, usuario_id: str, tenant_id: str, unidade_solicitada: str | None = None
    ) -> str:
        vinculos = [
            v
            for v in self._unidades
            if v.usuario_id == usuario_id and v.tenant_id == tenant_id
        ]
        if unidade_solicitada and any(
            v.unidade_id == unidade_solicitada for v in vinculos
        ):
            return unidade_solicitada
        if unidade_solicitada:
            raise UnidadeNaoAutorizada("Recurso indisponivel")
        padrao = next((v for v in vinculos if v.padrao), None)
        if not padrao:
            raise UnidadeNaoAutorizada("Recurso indisponivel")
        return padrao.unidade_id
