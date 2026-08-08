"""Registro tipado e processador sincrono/idempotente de mensagens."""

from typing import Callable, Protocol, TypeAlias

from core.dominio.tempo import Clock
from core.seguranca.contexto import ContextoExecucao

from .erros import ContextoTenantDivergente, HandlerNaoEncontrado
from .modelos import (
    DeadLetter,
    EnvelopeMensagem,
    ResultadoProcessamento,
    StatusProcessamento,
)
from .observabilidade import MetricasEventos
from .repositorios import RepositorioDLQ, RepositorioInbox
from .retry import PoliticaRetry, normalizar_erro


class HandlerEvento(Protocol):
    def __call__(self, mensagem: EnvelopeMensagem) -> None: ...


Handler: TypeAlias = Callable[[EnvelopeMensagem], None]


class RegistroHandlers:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def registrar(self, event_type: str, handler: Handler) -> None:
        if not event_type.strip() or event_type in self._handlers:
            raise ValueError("Handler invalido ou ja registrado")
        self._handlers[event_type] = handler

    def obter(self, event_type: str) -> Handler:
        try:
            return self._handlers[event_type]
        except KeyError as exc:
            raise HandlerNaoEncontrado() from exc


class ProcessadorMensagens:
    def __init__(
        self,
        *,
        inbox: RepositorioInbox,
        dlq: RepositorioDLQ,
        handlers: RegistroHandlers,
        retry: PoliticaRetry,
        metricas: MetricasEventos,
        clock: Clock,
    ) -> None:
        self._inbox = inbox
        self._dlq = dlq
        self._handlers = handlers
        self._retry = retry
        self._metricas = metricas
        self._clock = clock

    def processar(
        self, mensagem: EnvelopeMensagem, contexto: ContextoExecucao | None = None
    ) -> ResultadoProcessamento:
        agora = self._clock.agora()
        self._metricas.incrementar("messages_received")
        if contexto is not None and (
            contexto.tenant_id != str(mensagem.tenant_id)
            or contexto.unidade_id != str(mensagem.unidade_id)
            or contexto.correlation_id != str(mensagem.correlation_id)
            or contexto.causation_id
            != (str(mensagem.causation_id) if mensagem.causation_id else None)
        ):
            raise ContextoTenantDivergente()
        registro = self._inbox.registrar(mensagem, agora)
        if self._inbox.ja_processada(mensagem.idempotency_key):
            self._metricas.incrementar("messages_duplicate")
            return ResultadoProcessamento(
                StatusProcessamento.DUPLICADO, mensagem.event_id, registro.tentativas
            )
        try:
            self._handlers.obter(mensagem.event_type)(mensagem)
        except Exception as exc:
            erro = normalizar_erro(exc)
            self._inbox.marcar_falha(mensagem.idempotency_key, erro)
            attempt = registro.tentativas
            self._metricas.incrementar("messages_failed")
            if self._retry.deve_tentar(erro, attempt):
                proxima = self._retry.next_attempt_at(agora, attempt)
                self._metricas.incrementar("messages_retry")
                return ResultadoProcessamento(
                    StatusProcessamento.RETRY, mensagem.event_id, attempt, proxima, erro
                )
            motivo = (
                "non_retryable"
                if erro.classificacao.value == "non_retryable"
                else "retry_exhausted"
            )
            self._dlq.adicionar(
                DeadLetter.criar(mensagem, motivo, erro, attempt, agora)
            )
            self._metricas.incrementar("messages_dlq")
            return ResultadoProcessamento(
                StatusProcessamento.DLQ, mensagem.event_id, attempt, erro=erro
            )
        self._inbox.marcar_processada(mensagem.idempotency_key, agora)
        self._metricas.incrementar("messages_processed")
        return ResultadoProcessamento(
            StatusProcessamento.PROCESSADO, mensagem.event_id, registro.tentativas + 1
        )
