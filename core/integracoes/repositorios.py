"""Portas de persistência e verificação para configurações externas."""

from __future__ import annotations

from typing import Protocol

from .modelos import ConfiguracaoServicoExterno


class ConflitoVersaoConfiguracao(RuntimeError):
    pass


class RepositorioConfiguracoesExternas(Protocol):
    def obter(
        self, *, tenant_id: str, unidade_id: str, configuracao_id: str
    ) -> ConfiguracaoServicoExterno | None: ...

    def listar(
        self, *, tenant_id: str, unidade_id: str
    ) -> tuple[ConfiguracaoServicoExterno, ...]: ...

    def salvar(
        self,
        configuracao: ConfiguracaoServicoExterno,
        *,
        versao_esperada: int,
    ) -> ConfiguracaoServicoExterno: ...


class PortaProntidaoCredenciais(Protocol):
    def faltantes(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        provedor: str,
        finalidades: tuple[str, ...],
    ) -> tuple[str, ...]: ...
