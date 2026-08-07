"""IDs e envelopes para rastrear cadeias de comandos e eventos."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .contexto import ContextoExecucao
from .erros import ContextoAusente


def iniciar_correlation_id() -> str:
    return str(uuid4())


def preservar_correlation_id(valor: str) -> str:
    if not valor or not valor.strip():
        raise ContextoAusente("correlation_id obrigatorio")
    return valor.strip()


def gerar_causation_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class EnvelopeCorrelacionado:
    payload: Any
    correlation_id: str
    causation_id: str
    origem: str


def propagar_contexto(
    contexto: ContextoExecucao, payload: Any, *, origem: str | None = None
) -> EnvelopeCorrelacionado:
    return EnvelopeCorrelacionado(
        payload,
        preservar_correlation_id(contexto.correlation_id),
        gerar_causation_id(),
        origem or contexto.origem,
    )


propagar_para_comando = propagar_contexto
propagar_para_evento = propagar_contexto
