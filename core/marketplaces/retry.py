"""Retry externo com backoff exponencial e jitter determinístico testável."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from core.eventos.retry import PoliticaRetry


@dataclass(frozen=True)
class PoliticaRetryMarketplace(PoliticaRetry):
    jitter_ratio: float = 0.20

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.jitter_ratio < 0 or self.jitter_ratio > 1:
            raise ValueError("jitter_ratio invalido")

    def next_attempt_at(self, agora: datetime, attempt: int) -> datetime:
        base = self.backoff(attempt)
        fracao = ((attempt * 37) % 10) / 10
        jitter = base.total_seconds() * self.jitter_ratio * fracao
        return agora + base + timedelta(seconds=jitter)
