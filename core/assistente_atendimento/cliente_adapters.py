"""Portas para identificação e contexto de cliente no atendimento."""

from __future__ import annotations

from typing import Protocol

from core.seguranca.contexto import ContextoExecucao

from .contexto import ClienteAtendimento


class PortaClientesAtendimento(Protocol):
    def identificar_por_canal(
        self,
        *,
        contexto: ContextoExecucao,
        canal: str,
        identificador_externo: str,
    ) -> ClienteAtendimento:
        """Resolve cliente somente dentro do tenant/unidade autorizado."""
        ...
