"""Fitness F14-C: contratos canônicos de eventos, idempotência e resiliência."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    TenantId,
    UnidadeId,
)
from core.dominio.tempo import FixedClock
from core.eventos.erros import MensagemInvalida
from core.eventos.modelos import EnvelopeMensagem, StatusProcessamento
from core.eventos.observabilidade import ColetorMetricasEmMemoria
from core.eventos.processador import ProcessadorMensagens, RegistroHandlers
from core.eventos.repositorios import (
    RepositorioDLQEmMemoria,
    RepositorioInboxEmMemoria,
)
from core.eventos.retry import PoliticaRetry
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.eventos.modelos_orm import EventBusBase

AGORA = datetime(2026, 9, 6, 5, 30, tzinfo=timezone.utc)
CAMPOS_CANONICOS = {
    "event_id",
    "event_type",
    "aggregate_id",
    "aggregate_type",
    "tenant_id",
    "unit_id",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "timestamp",
    "version",
    "payload",
}
CAMPOS_F14C_OBRIGATORIOS = {
    "event_id",
    "event_type",
    "aggregate_id",
    "tenant_id",
    "unit_id",
    "correlation_id",
    "causation_id",
    "idempotency_key",
    "timestamp",
    "version",
    "payload",
}


def _envelope(
    numero: int = 1,
    *,
    event_type: str = "pdv.venda_confirmada",
    chave: str | None = None,
    instante: datetime = AGORA,
    payload: dict[str, Any] | None = None,
) -> EnvelopeMensagem:
    return EnvelopeMensagem(
        event_id=EventoId.de(f"evt-f14c-{numero}"),
        event_type=event_type,
        aggregate_id=f"venda-f14c-{numero}",
        aggregate_type="venda",
        tenant_id=TenantId.de("tenant-f14c"),
        unidade_id=UnidadeId.de("unidade-f14c"),
        correlation_id=CorrelationId.de("corr-f14c"),
        causation_id=CausationId.de("cause-f14c"),
        idempotency_key=IdempotencyKey.de(chave or f"idem-f14c-{numero}"),
        occurred_at=instante,
        payload=payload
        if payload is not None
        else {"pedido_id": f"pedido-{numero}", "itens": [{"sku": "A", "qtd": 1}]},
        version=1,
    )


def _contexto_valido() -> ContextoExecucao:
    contexto = ContextoExecucao.sistema(
        identidade="worker-f14c",
        motivo="fitness-eventos",
        tenant_id="tenant-f14c",
        unidade_id="unidade-f14c",
        correlation_id="corr-f14c",
        solicitado_em=AGORA,
    )
    return replace(contexto, causation_id="cause-f14c")


def _processador(
    handler,
    *,
    event_type: str = "pdv.venda_confirmada",
) -> tuple[
    ProcessadorMensagens,
    RepositorioInboxEmMemoria,
    RepositorioDLQEmMemoria,
    ColetorMetricasEmMemoria,
]:
    inbox = RepositorioInboxEmMemoria()
    dlq = RepositorioDLQEmMemoria()
    metricas = ColetorMetricasEmMemoria()
    handlers = RegistroHandlers()
    handlers.registrar(event_type, handler)
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


def test_envelope_canonico_e_estrito_com_payload_profundo_imutavel() -> None:
    evento = _envelope()
    canonico = evento.para_dict_canonico()

    assert set(canonico) == CAMPOS_CANONICOS
    assert CAMPOS_F14C_OBRIGATORIOS <= set(canonico)
    assert canonico["unit_id"] == "unidade-f14c"
    assert canonico["timestamp"] == "2026-09-06T05:30:00Z"
    assert "unidade_id" not in canonico
    assert "occurred_at" not in canonico
    assert EnvelopeMensagem.de_dict_canonico(canonico) == evento

    for campo in CAMPOS_F14C_OBRIGATORIOS:
        incompleto = dict(canonico)
        incompleto.pop(campo)
        with pytest.raises(MensagemInvalida):
            EnvelopeMensagem.de_dict_canonico(incompleto)

    inesperado = dict(canonico)
    inesperado["extra"] = "nao-permitido"
    with pytest.raises(MensagemInvalida):
        EnvelopeMensagem.de_dict_canonico(inesperado)

    with pytest.raises(TypeError):
        evento.payload["novo"] = True  # type: ignore[index]
    with pytest.raises(TypeError):
        evento.payload["itens"][0]["qtd"] = 99  # type: ignore[index]

    payload_serializado = canonico["payload"]
    payload_serializado["itens"][0]["qtd"] = 99
    assert evento.payload["itens"][0]["qtd"] == 1


def test_replay_nao_duplica_mutacoes_em_kds_crm_ou_salao() -> None:
    evento = _envelope()
    projecoes = {"kds": 0, "crm": 0, "salao": 0}

    for consumidor in projecoes:
        def handler(_: EnvelopeMensagem, nome: str = consumidor) -> None:
            projecoes[nome] += 1

        proc, _, dlq, _ = _processador(handler)
        primeiro = proc.processar(evento, _contexto_valido())
        replay = proc.processar(evento, _contexto_valido())

        assert primeiro.status is StatusProcessamento.PROCESSADO
        assert replay.status is StatusProcessamento.DUPLICADO
        assert not dlq.listar()

    assert projecoes == {"kds": 1, "crm": 1, "salao": 1}


def test_retry_transitorio_termina_uma_vez_sem_duplicar_mutacao() -> None:
    chamadas = 0
    mutacoes = 0

    def handler(_: EnvelopeMensagem) -> None:
        nonlocal chamadas, mutacoes
        chamadas += 1
        if chamadas == 1:
            raise RuntimeError("falha transitoria")
        mutacoes += 1

    proc, _, dlq, metricas = _processador(
        handler, event_type="pagamentos.confirmado"
    )
    evento = _envelope(2, event_type="pagamentos.confirmado")

    primeiro = proc.processar(evento, _contexto_valido())
    segundo = proc.processar(evento, _contexto_valido())
    replay = proc.processar(evento, _contexto_valido())

    assert primeiro.status is StatusProcessamento.RETRY
    assert segundo.status is StatusProcessamento.PROCESSADO
    assert replay.status is StatusProcessamento.DUPLICADO
    assert chamadas == 2
    assert mutacoes == 1
    assert metricas.valor("messages_retry") == 1
    assert not dlq.listar()


def test_outbox_duravel_ordena_por_timestamp_antes_da_publicacao() -> None:
    engine = create_engine("sqlite:///:memory:")
    EventBusBase.metadata.create_all(engine)
    mais_tarde = _envelope(3, instante=AGORA + timedelta(seconds=10))
    mais_cedo = _envelope(4, instante=AGORA)

    with Session(engine) as session:
        outbox = RepositorioOutboxSQLAlchemy(session)
        outbox.adicionar(mais_tarde)
        outbox.adicionar(mais_cedo)
        session.commit()

        pendentes = outbox.pendentes(10, AGORA + timedelta(minutes=1))

    assert [evento.event_id for evento in pendentes] == [
        mais_cedo.event_id,
        mais_tarde.event_id,
    ]


def test_payload_malformado_de_dominio_vai_dlq_e_fila_principal_continua() -> None:
    mutacoes = 0

    def handler(evento: EnvelopeMensagem) -> None:
        nonlocal mutacoes
        if "pedido_id" not in evento.payload:
            raise MensagemInvalida()
        mutacoes += 1

    proc, _, dlq, metricas = _processador(handler)
    malformado = _envelope(5, payload={"itens": []})
    valido = _envelope(6)

    rejeitado = proc.processar(malformado, _contexto_valido())
    processado = proc.processar(valido, _contexto_valido())

    assert rejeitado.status is StatusProcessamento.DLQ
    assert rejeitado.erro is not None
    assert rejeitado.erro.tipo == "MensagemInvalida"
    assert dlq.listar()[0].motivo == "non_retryable"
    assert processado.status is StatusProcessamento.PROCESSADO
    assert mutacoes == 1
    assert metricas.valor("messages_dlq") == 1
    assert metricas.valor("messages_processed") == 1


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("tenant_id", "tenant-invasor"),
        ("unidade_id", "unidade-invasora"),
        ("correlation_id", "corr-invasora"),
        ("causation_id", "cause-invasora"),
    ],
)
def test_contexto_divergente_vai_dlq_sem_handler_ou_vazamento(
    campo: str, valor: str
) -> None:
    mutacoes = 0

    def handler(_: EnvelopeMensagem) -> None:
        nonlocal mutacoes
        mutacoes += 1

    proc, inbox, dlq, metricas = _processador(handler)
    evento = _envelope(7)
    contexto = replace(_contexto_valido(), **{campo: valor})

    resultado = proc.processar(evento, contexto)

    assert resultado.status is StatusProcessamento.DLQ
    assert resultado.attempts == 0
    assert resultado.erro is not None
    assert resultado.erro.tipo == "ContextoTenantDivergente"
    assert mutacoes == 0
    assert not inbox.historico()
    assert len(dlq.listar()) == 1
    dead = dlq.listar()[0]
    assert dead.motivo == "context_mismatch"
    assert dead.tenant_id == evento.tenant_id
    assert dead.unidade_id == evento.unidade_id
    assert dead.correlation_id == evento.correlation_id
    assert dead.mensagem.causation_id == evento.causation_id
    assert metricas.valor("messages_dlq") == 1

    seguinte = _envelope(8)
    assert (
        proc.processar(seguinte, _contexto_valido()).status
        is StatusProcessamento.PROCESSADO
    )
    assert mutacoes == 1


def test_conflito_de_inbox_vai_dlq_e_nao_interrompe_proximo_evento() -> None:
    mutacoes = 0

    def handler(_: EnvelopeMensagem) -> None:
        nonlocal mutacoes
        mutacoes += 1

    proc, _, dlq, _ = _processador(handler)
    original = _envelope(9, chave="idem-f14c-conflito")
    conflitante = _envelope(10, chave="idem-f14c-conflito")
    seguinte = _envelope(11)

    assert (
        proc.processar(original, _contexto_valido()).status
        is StatusProcessamento.PROCESSADO
    )
    conflito = proc.processar(conflitante, _contexto_valido())
    assert conflito.status is StatusProcessamento.DLQ
    assert conflito.erro is not None
    assert conflito.erro.tipo == "ConflitoInbox"
    assert dlq.listar()[0].motivo == "inbox_conflict"

    assert (
        proc.processar(seguinte, _contexto_valido()).status
        is StatusProcessamento.PROCESSADO
    )
    assert mutacoes == 2
