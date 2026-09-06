from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.dominio.tempo import FixedClock
from core.eventos.erros import ConflitoInbox, DuplicataOutbox
from core.eventos.modelos import (
    ClassificacaoErro,
    DeadLetter,
    EnvelopeMensagem,
    ErroNormalizado,
    StatusProcessamento,
)
from core.eventos.observabilidade import ColetorMetricasEmMemoria
from core.eventos.processador import ProcessadorMensagens, RegistroHandlers
from core.eventos.repositorios import (
    RepositorioDLQEmMemoria,
    RepositorioInboxEmMemoria,
    RepositorioOutboxEmMemoria,
    StatusOutbox,
)
from core.eventos.retry import ErroNaoRetryable, PoliticaRetry
from core.seguranca.contexto import ContextoExecucao

AGORA = datetime(2026, 8, 8, tzinfo=timezone.utc)


def mensagem(numero: int = 1, *, chave: str | None = None) -> EnvelopeMensagem:
    return EnvelopeMensagem(
        EventoId.de(f"evento-{numero}"),
        "pedido.criado",
        f"pedido-{numero}",
        "pedido",
        TenantId.de("tenant-1"),
        UnidadeId.de("unidade-1"),
        CorrelationId.de("corr-1"),
        CausationId.de("cause-1"),
        IdempotencyKey.de(chave or f"key-{numero}"),
        AGORA,
        {"item": {"quantidade": 1}, "lista": [1, 2]},
        1,
    )


def processador(handler):
    inbox, dlq, metricas = (
        RepositorioInboxEmMemoria(),
        RepositorioDLQEmMemoria(),
        ColetorMetricasEmMemoria(),
    )
    handlers = RegistroHandlers()
    if handler is not None:
        handlers.registrar("pedido.criado", handler)
    return (
        ProcessadorMensagens(
            inbox=inbox,
            dlq=dlq,
            handlers=handlers,
            retry=PoliticaRetry(max_attempts=3),
            metricas=metricas,
            clock=FixedClock(AGORA),
        ),
        inbox,
        dlq,
        metricas,
    )


def test_envelope_imutavel_serializavel_e_preserva_ids() -> None:
    evento = mensagem()
    with pytest.raises(FrozenInstanceError):
        evento.event_type = "outro"  # type: ignore[misc]
    with pytest.raises(TypeError):
        evento.payload["novo"] = 1  # type: ignore[index]
    dados = evento.para_dict()
    assert dados["occurred_at"] == "2026-08-08T00:00:00Z"
    assert dados["correlation_id"] == "corr-1"
    assert dados["causation_id"] == "cause-1"


def test_outbox_duplicata_estado_e_ordem_deterministica() -> None:
    outbox = RepositorioOutboxEmMemoria()
    primeiro, segundo = mensagem(1), mensagem(2)
    assert outbox.adicionar(primeiro) is outbox.adicionar(primeiro)
    outbox.adicionar(segundo)
    assert [r.mensagem.event_id for r in outbox.listar_pendentes()] == [
        primeiro.event_id,
        segundo.event_id,
    ]
    with pytest.raises(DuplicataOutbox):
        outbox.adicionar(mensagem(3, chave="key-1"))
    outbox.marcar_publicado(primeiro.event_id)
    outbox.marcar_publicado(primeiro.event_id)
    assert outbox.consultar(event_id=primeiro.event_id).status is StatusOutbox.PUBLICADO  # type: ignore[union-attr]


def test_inbox_replay_e_conflito() -> None:
    inbox = RepositorioInboxEmMemoria()
    original = mensagem()
    assert inbox.registrar(original, AGORA) is inbox.registrar(original, AGORA)
    inbox.marcar_processada(original.idempotency_key, AGORA)
    assert inbox.ja_processada(original.idempotency_key)
    with pytest.raises(ConflitoInbox):
        inbox.registrar(mensagem(2, chave="key-1"), AGORA)


def test_handler_executa_exatamente_uma_vez_e_metricas() -> None:
    chamadas: list[EnvelopeMensagem] = []
    proc, _, _, metricas = processador(chamadas.append)
    assert proc.processar(mensagem()).status is StatusProcessamento.PROCESSADO
    assert proc.processar(mensagem()).status is StatusProcessamento.DUPLICADO
    assert len(chamadas) == 1
    assert metricas.valor("messages_received") == 2
    assert metricas.valor("messages_processed") == 1
    assert metricas.valor("messages_duplicate") == 1


def test_retry_uma_vez_entao_sucesso_sem_sleep() -> None:
    chamadas = 0

    def handler(_: EnvelopeMensagem) -> None:
        nonlocal chamadas
        chamadas += 1
        if chamadas == 1:
            raise RuntimeError("temporario")

    proc, _, dlq, metricas = processador(handler)
    primeiro = proc.processar(mensagem())
    assert primeiro.status is StatusProcessamento.RETRY
    assert primeiro.next_attempt_at and primeiro.next_attempt_at > AGORA
    assert proc.processar(mensagem()).status is StatusProcessamento.PROCESSADO
    assert not dlq.listar()
    assert metricas.valor("messages_retry") == 1


def test_retry_esgotado_vai_para_dlq() -> None:
    def falhar(_: EnvelopeMensagem) -> None:
        raise RuntimeError("temporario")

    proc, _, dlq, metricas = processador(falhar)
    resultados = [proc.processar(mensagem()) for _ in range(3)]
    assert [r.status for r in resultados] == [
        StatusProcessamento.RETRY,
        StatusProcessamento.RETRY,
        StatusProcessamento.DLQ,
    ]
    assert dlq.listar()[0].motivo == "retry_exhausted"
    assert metricas.valor("messages_failed") == 3
    assert metricas.valor("messages_dlq") == 1


def test_erro_nao_retryable_vai_para_dlq_imediatamente() -> None:
    def falhar(_: EnvelopeMensagem) -> None:
        raise ErroNaoRetryable("entrada recusada")

    proc, _, dlq, _ = processador(falhar)
    assert proc.processar(mensagem()).status is StatusProcessamento.DLQ
    assert dlq.listar()[0].tentativas == 1
    assert dlq.listar()[0].motivo == "non_retryable"


def test_handler_inexistente_resulta_em_dlq_imediata() -> None:
    proc, _, dlq, _ = processador(None)
    resultado = proc.processar(mensagem())
    assert resultado.status is StatusProcessamento.DLQ
    assert resultado.erro and resultado.erro.tipo == "HandlerNaoEncontrado"
    assert dlq.listar()[0].motivo == "non_retryable"


def test_contexto_divergente_vai_para_dlq_sem_interromper_consumidor() -> None:
    chamadas: list[EnvelopeMensagem] = []
    proc, inbox, dlq, metricas = processador(chamadas.append)
    contexto = ContextoExecucao.sistema(
        identidade="worker",
        motivo="processar",
        tenant_id="tenant-2",
        unidade_id="unidade-1",
        correlation_id="corr-1",
        solicitado_em=AGORA,
    )

    resultado = proc.processar(mensagem(), contexto)

    assert resultado.status is StatusProcessamento.DLQ
    assert resultado.erro and resultado.erro.tipo == "ContextoTenantDivergente"
    assert not chamadas
    assert not inbox.historico()
    assert dlq.listar()[0].motivo == "context_mismatch"
    assert metricas.valor("messages_dlq") == 1


def test_dlq_sanitiza_metadata_e_preserva_contexto() -> None:
    msg = mensagem()
    erro = ErroNormalizado("Erro", "seguro", ClassificacaoErro.NON_RETRYABLE)
    item = DeadLetter.criar(
        msg, "fatal", erro, 1, AGORA, {"token": "x", "authorization": "x", "safe": "ok"}
    )
    assert dict(item.metadata) == {"safe": "ok"}
    assert item.tenant_id == msg.tenant_id
    assert item.unidade_id == msg.unidade_id
    assert item.correlation_id == msg.correlation_id


def test_registry_rejeita_registro_duplicado() -> None:
    registry = RegistroHandlers()
    registry.registrar("tipo", lambda _: None)
    with pytest.raises(ValueError):
        registry.registrar("tipo", lambda _: None)
