"""Erros estaveis e seguros da infraestrutura de eventos."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ErroEventos(Exception):
    codigo: str
    mensagem: str

    def __str__(self) -> str:
        return self.mensagem

    def para_dict(self) -> dict[str, Any]:
        return {"code": self.codigo, "message": self.mensagem}


class MensagemDuplicada(ErroEventos):
    def __init__(self) -> None:
        super().__init__("duplicate_message", "Mensagem ja recebida")


class HandlerNaoEncontrado(ErroEventos):
    def __init__(self) -> None:
        super().__init__("handler_not_found", "Handler nao encontrado")


class RetryEsgotado(ErroEventos):
    def __init__(self) -> None:
        super().__init__("retry_exhausted", "Tentativas esgotadas")


class MensagemInvalida(ErroEventos):
    def __init__(self) -> None:
        super().__init__("invalid_message", "Mensagem invalida")


class ContextoTenantDivergente(ErroEventos):
    def __init__(self) -> None:
        super().__init__("tenant_context_mismatch", "Contexto da mensagem divergente")


class DuplicataOutbox(ErroEventos):
    def __init__(self) -> None:
        super().__init__("outbox_duplicate", "Evento duplicado na outbox")


class ConflitoInbox(ErroEventos):
    def __init__(self) -> None:
        super().__init__("inbox_conflict", "Chave da inbox pertence a outra mensagem")
