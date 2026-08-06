from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from .erros import ErroValidacaoDominio


def em_utc(instante: datetime) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ErroValidacaoDominio("Datetime deve conter timezone")
    return instante.astimezone(timezone.utc)


class Clock(ABC):
    @abstractmethod
    def agora(self) -> datetime: ...


class SystemClock(Clock):
    def agora(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedClock(Clock):
    instante: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instante", em_utc(self.instante))

    def agora(self) -> datetime:
        return self.instante
