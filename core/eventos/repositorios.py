"""Portas outbox/inbox/DLQ e adapters deterministicos em memoria."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from core.dominio.ids import EventoId, IdempotencyKey

from .erros import ConflitoInbox, DuplicataOutbox
from .modelos import DeadLetter, EnvelopeMensagem, ErroNormalizado


class StatusOutbox(str, Enum):
    PENDENTE = "pending"
    PUBLICADO = "published"
    FALHA = "failed"


@dataclass
class RegistroOutbox:
    mensagem: EnvelopeMensagem
    status: StatusOutbox = StatusOutbox.PENDENTE
    tentativas: int = 0
    ultimo_erro: ErroNormalizado | None = None


class RepositorioOutbox(Protocol):
    def adicionar(self, mensagem: EnvelopeMensagem) -> RegistroOutbox: ...
    def listar_pendentes(self) -> tuple[RegistroOutbox, ...]: ...
    def marcar_publicado(self, event_id: EventoId) -> None: ...
    def marcar_tentativa(self, event_id: EventoId) -> None: ...
    def marcar_falha(self, event_id: EventoId, erro: ErroNormalizado) -> None: ...
    def consultar(
        self,
        *,
        event_id: EventoId | None = None,
        idempotency_key: IdempotencyKey | None = None,
    ) -> RegistroOutbox | None: ...


class RepositorioOutboxEmMemoria:
    def __init__(self) -> None:
        self._registros: list[RegistroOutbox] = []

    def adicionar(self, mensagem: EnvelopeMensagem) -> RegistroOutbox:
        existente = self.consultar(idempotency_key=mensagem.idempotency_key)
        if existente:
            if existente.mensagem.event_id == mensagem.event_id:
                return existente
            raise DuplicataOutbox()
        if self.consultar(event_id=mensagem.event_id):
            raise DuplicataOutbox()
        registro = RegistroOutbox(mensagem)
        self._registros.append(registro)
        return registro

    def listar_pendentes(self) -> tuple[RegistroOutbox, ...]:
        return tuple(r for r in self._registros if r.status is StatusOutbox.PENDENTE)

    def _obter(self, event_id: EventoId) -> RegistroOutbox:
        registro = self.consultar(event_id=event_id)
        if registro is None:
            raise KeyError(str(event_id))
        return registro

    def marcar_publicado(self, event_id: EventoId) -> None:
        registro = self._obter(event_id)
        if registro.status is not StatusOutbox.PUBLICADO:
            registro.status = StatusOutbox.PUBLICADO

    def marcar_tentativa(self, event_id: EventoId) -> None:
        self._obter(event_id).tentativas += 1

    def marcar_falha(self, event_id: EventoId, erro: ErroNormalizado) -> None:
        registro = self._obter(event_id)
        registro.status, registro.ultimo_erro = StatusOutbox.FALHA, erro

    def consultar(
        self,
        *,
        event_id: EventoId | None = None,
        idempotency_key: IdempotencyKey | None = None,
    ) -> RegistroOutbox | None:
        return next(
            (
                r
                for r in self._registros
                if (event_id is not None and r.mensagem.event_id == event_id)
                or (
                    idempotency_key is not None
                    and r.mensagem.idempotency_key == idempotency_key
                )
            ),
            None,
        )


@dataclass
class RegistroInbox:
    mensagem: EnvelopeMensagem
    recebido_em: datetime
    processado_em: datetime | None = None
    tentativas: int = 0
    ultimo_erro: ErroNormalizado | None = None


class RepositorioInbox(Protocol):
    def registrar(
        self, mensagem: EnvelopeMensagem, recebido_em: datetime
    ) -> RegistroInbox: ...
    def ja_processada(self, chave: IdempotencyKey) -> bool: ...
    def marcar_processada(self, chave: IdempotencyKey, instante: datetime) -> None: ...
    def marcar_falha(self, chave: IdempotencyKey, erro: ErroNormalizado) -> None: ...
    def historico(self) -> tuple[RegistroInbox, ...]: ...


class RepositorioInboxEmMemoria:
    def __init__(self) -> None:
        self._registros: dict[IdempotencyKey, RegistroInbox] = {}

    def registrar(
        self, mensagem: EnvelopeMensagem, recebido_em: datetime
    ) -> RegistroInbox:
        existente = self._registros.get(mensagem.idempotency_key)
        if existente:
            if existente.mensagem.event_id != mensagem.event_id:
                raise ConflitoInbox()
            return existente
        registro = RegistroInbox(mensagem, recebido_em)
        self._registros[mensagem.idempotency_key] = registro
        return registro

    def ja_processada(self, chave: IdempotencyKey) -> bool:
        registro = self._registros.get(chave)
        return bool(registro and registro.processado_em is not None)

    def marcar_processada(self, chave: IdempotencyKey, instante: datetime) -> None:
        self._registros[chave].processado_em = instante

    def marcar_falha(self, chave: IdempotencyKey, erro: ErroNormalizado) -> None:
        registro = self._registros[chave]
        registro.tentativas += 1
        registro.ultimo_erro = erro

    def historico(self) -> tuple[RegistroInbox, ...]:
        return tuple(self._registros.values())


class RepositorioDLQ(Protocol):
    def adicionar(self, item: DeadLetter) -> None: ...
    def listar(self) -> tuple[DeadLetter, ...]: ...


class RepositorioDLQEmMemoria:
    def __init__(self) -> None:
        self._itens: list[DeadLetter] = []

    def adicionar(self, item: DeadLetter) -> None:
        self._itens.append(item)

    def listar(self) -> tuple[DeadLetter, ...]:
        return tuple(self._itens)
