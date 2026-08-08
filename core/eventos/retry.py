"""Politica de retry pura, sem espera ou efeitos de IO."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from .modelos import ClassificacaoErro, ErroNormalizado
from .erros import ErroEventos


@dataclass(frozen=True)
class PoliticaRetry:
    max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.backoff_base_seconds < 0:
            raise ValueError("Politica de retry invalida")

    def backoff(self, attempt: int) -> timedelta:
        segundos = min(
            self.backoff_base_seconds * (2 ** max(0, attempt - 1)),
            self.backoff_max_seconds,
        )
        return timedelta(seconds=segundos)

    def next_attempt_at(self, agora: datetime, attempt: int) -> datetime:
        return agora + self.backoff(attempt)

    def deve_tentar(self, erro: ErroNormalizado, attempt: int) -> bool:
        return (
            erro.classificacao is ClassificacaoErro.RETRYABLE
            and attempt < self.max_attempts
        )


def normalizar_erro(erro: Exception) -> ErroNormalizado:
    classificacao = (
        ClassificacaoErro.NON_RETRYABLE
        if isinstance(erro, (ErroNaoRetryable, ErroEventos))
        else ClassificacaoErro.RETRYABLE
    )
    return ErroNormalizado(type(erro).__name__, str(erro)[:200], classificacao)


class ErroNaoRetryable(Exception):
    """Handler pode usar este erro para impedir retries sem vazar detalhes."""
