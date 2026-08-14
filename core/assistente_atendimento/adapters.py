"""Portas da configuração de identidade do Assistente de Atendimento."""

from typing import Any, Protocol

from .modelos import ConfiguracaoIdentidadeAssistente


class RepositorioIdentidadeAssistente(Protocol):
    def obter(self, *, tenant_id: str, unidade_id: str) -> ConfiguracaoIdentidadeAssistente | None: ...

    def salvar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        nome_publico: str,
        atributos: dict[str, Any],
        atualizado_por: str,
        correlation_id: str,
        versao_esperada: int | None,
    ) -> ConfiguracaoIdentidadeAssistente: ...
