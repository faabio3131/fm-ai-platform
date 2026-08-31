"""Contexto seguro de uma conversa do Agente Inteligente de Atendimento."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from core.seguranca.contexto import ContextoExecucao

from .customer_context import ContextoClienteAutorizado


class TipoClienteAtendimento(StrEnum):
    CONHECIDO = "conhecido"
    NOVO = "novo"


@dataclass(frozen=True, kw_only=True)
class ClienteAtendimento:
    tipo: TipoClienteAtendimento
    cliente_ref: str | None
    nome: str | None = None

    def __post_init__(self) -> None:
        if (
            self.tipo is TipoClienteAtendimento.CONHECIDO
            and (self.cliente_ref is None or not self.cliente_ref.strip())
        ):
            raise ValueError("cliente_conhecido_exige_referencia")


@dataclass(frozen=True, kw_only=True)
class ContextoAtendimento:
    contexto_execucao: ContextoExecucao
    conversa_id: str
    canal: str
    cliente: ClienteAtendimento
    customer_context: ContextoClienteAutorizado | None = None

    def __post_init__(self) -> None:
        if not self.conversa_id.strip():
            raise ValueError("conversa_id_obrigatorio")
        if not self.canal.strip():
            raise ValueError("canal_obrigatorio")
        if (
            self.customer_context is not None
            and self.customer_context.cliente_ref != self.cliente.cliente_ref
        ):
            raise ValueError("customer_context_de_outro_cliente")

    @property
    def tenant_id(self) -> str:
        return self.contexto_execucao.tenant_id

    @property
    def unidade_id(self) -> str:
        return self.contexto_execucao.unidade_id
