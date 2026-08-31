"""Portas do domínio operacional do Assistente de Atendimento V1."""

from __future__ import annotations

from typing import Protocol

from core.pagamentos.modelos import MetodoPagamento
from core.seguranca.contexto import ContextoExecucao

from .atendimento_modelos import CarrinhoAtendimento, ResultadoCheckoutAssistente


class PortaCheckoutAssistente(Protocol):
    def executar(
        self,
        *,
        contexto: ContextoExecucao,
        carrinho: CarrinhoAtendimento,
        cliente_ref: str,
        canal: str,
        metodo: MetodoPagamento,
        idempotency_key: str,
    ) -> ResultadoCheckoutAssistente: ...


class PortaHandoffAssistente(Protocol):
    def registrar(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
        motivo: str,
        metadata_segura: dict[str, str | int | bool] | None = None,
    ) -> None: ...
