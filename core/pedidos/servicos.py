"""Casos de uso autoritativos de Pedido V1.

A regra central é: agregado, histórico do pedido, Outbox e auditoria são escritos
pela mesma unidade de trabalho. Nenhum canal deve atualizar status diretamente.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from typing import Protocol
from uuid import uuid4

from core.dominio.decisoes import DecisaoCozinha
from core.dominio.enums import PedidoStatus
from core.dominio.erros import (
    ConflitoIdempotencia,
    PermissaoNegada,
    RecursoNaoEncontrado,
)
from core.dominio.eventos import EventoPedidoOperacional, PedidoCriado
from core.dominio.ids import (
    CausationId,
    CorrelationId,
    EventoId,
    IdempotencyKey,
    PedidoId,
    TenantId,
    UnidadeId,
)
from core.dominio.pedidos import Pedido
from core.estados.maquinas import ComandoTransicao, SnapshotEstado, transicionar
from core.eventos.modelos import EnvelopeMensagem
from core.seguranca import AutorizarAcao, ContextoExecucao, Permissao
from core.seguranca.auditoria import (
    EventoAuditoria,
    RepositorioAuditoria,
    sanitizar_metadata,
)

from .repositorios import RepositorioPedidos

_REQUEST_FINGERPRINT_KEY = "_request_fingerprint"


class PortaOutboxPedidos(Protocol):
    def adicionar(self, mensagem: EnvelopeMensagem) -> None: ...

    def consultar(
        self,
        *,
        tenant_id: TenantId,
        unidade_id: UnidadeId,
        event_id: EventoId | None = None,
        idempotency_key: IdempotencyKey | None = None,
    ) -> EnvelopeMensagem | None: ...


@dataclass(frozen=True)
class ResultadoPedidoAutoritativo:
    pedido: Pedido
    evento: EnvelopeMensagem
    auditoria: EventoAuditoria | None
    idempotente: bool = False


def _envelope(evento: PedidoCriado | EventoPedidoOperacional) -> EnvelopeMensagem:
    if evento.idempotency_key is None:
        raise ValueError("evento autoritativo exige idempotency_key")
    return EnvelopeMensagem(
        event_id=evento.event_id,
        event_type=evento.event_type,
        aggregate_id=evento.aggregate_id,
        aggregate_type=evento.aggregate_type,
        tenant_id=evento.tenant_id,
        unidade_id=evento.unidade_id,
        correlation_id=evento.correlation_id,
        causation_id=evento.causation_id,
        idempotency_key=evento.idempotency_key,
        occurred_at=evento.occurred_at,
        payload=evento.payload,
        version=evento.version,
    )


def _validar_contexto(pedido: Pedido, contexto: ContextoExecucao) -> None:
    if (
        str(pedido.tenant_id) != contexto.tenant_id
        or str(pedido.unidade_id) != contexto.unidade_id
    ):
        raise PermissaoNegada("Pedido fora do tenant/unidade ativo")


def _fingerprint_transicao(
    *,
    destino: PedidoStatus,
    versao_esperada: int,
    motivo: str | None,
    precondicoes: Mapping[str, bool],
) -> str:
    """Fingerprint durável com a mesma semântica usada pela máquina normativa."""

    payload = {
        "destino": destino.value,
        "versao": versao_esperada,
        "motivo": motivo,
        "pre": sorted(precondicoes.items()),
    }
    return sha256(
        dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _auditoria_criacao(
    pedido: Pedido, contexto: ContextoExecucao, *, timestamp: datetime
) -> EventoAuditoria:
    papel = next(iter(sorted(contexto.papeis, key=str)), None)
    return EventoAuditoria(
        audit_id=str(uuid4()),
        tenant_id=contexto.tenant_id,
        unidade_id=contexto.unidade_id,
        usuario_id=contexto.usuario_id,
        papel_efetivo=papel,
        acao="pedido.criado",
        recurso_tipo="pedido",
        recurso_id=str(pedido.id),
        resultado="permitido",
        motivo="criacao_autoritativa",
        correlation_id=contexto.correlation_id,
        timestamp=timestamp,
        origem=contexto.origem,
        politica="rbac_pedido_alterar",
        causation_id=contexto.causation_id,
        depois_resumido=(
            ("estado", pedido.status.value),
            ("origem", pedido.origem.value),
            ("canal", pedido.canal.value),
        ),
        metadata=sanitizar_metadata({"quantidade_itens": len(pedido.itens)}),
    )


def registrar_novo_pedido(
    *,
    pedido: Pedido,
    contexto: ContextoExecucao,
    repositorio: RepositorioPedidos,
    outbox: PortaOutboxPedidos,
    auditoria: RepositorioAuditoria,
    autorizador: AutorizarAcao | None = None,
) -> ResultadoPedidoAutoritativo:
    """Persiste um novo rascunho e seu evento na mesma transação externa."""

    _validar_contexto(pedido, contexto)
    decisao = (autorizador or AutorizarAcao()).executar(
        contexto=contexto,
        permissao=Permissao.PEDIDO_ALTERAR,
        recurso="pedido",
        tenant_recurso=str(pedido.tenant_id),
        unidade_recurso=str(pedido.unidade_id),
    )
    if not decisao.autorizado:
        raise PermissaoNegada(decisao.codigo)

    repetido = outbox.consultar(
        tenant_id=pedido.tenant_id,
        unidade_id=pedido.unidade_id,
        idempotency_key=pedido.idempotency_key,
    )
    if repetido is not None:
        existente = repositorio.buscar_por_idempotencia(
            pedido.tenant_id, pedido.unidade_id, pedido.idempotency_key
        )
        if (
            existente is None
            or repetido.aggregate_id != str(existente.id)
            or repetido.event_type != "pedidocriado.v1"
        ):
            raise ConflitoIdempotencia("idempotency_key reutilizada em outra operação")
        return ResultadoPedidoAutoritativo(existente, repetido, None, True)

    persistido = repositorio.salvar(pedido)
    instante = datetime.now(timezone.utc)
    evento = PedidoCriado(
        event_id=EventoId(str(uuid4())),
        aggregate_id=str(persistido.id),
        aggregate_type="pedido",
        tenant_id=persistido.tenant_id,
        unidade_id=persistido.unidade_id,
        correlation_id=persistido.correlation_id,
        causation_id=CausationId(contexto.causation_id) if contexto.causation_id else None,
        occurred_at=instante,
        idempotency_key=persistido.idempotency_key,
        payload={
            "status": persistido.status.value,
            "origem": persistido.origem.value,
            "canal": persistido.canal.value,
            "total": str(persistido.total.valor),
            "quantidade_itens": len(persistido.itens),
        },
        version=persistido.versao,
    )
    repositorio.salvar_eventos(
        persistido.tenant_id,
        persistido.unidade_id,
        persistido.id,
        (evento,),
    )
    envelope = _envelope(evento)
    outbox.adicionar(envelope)
    audit = _auditoria_criacao(persistido, contexto, timestamp=instante)
    auditoria.adicionar(audit)
    return ResultadoPedidoAutoritativo(persistido, envelope, audit)


def transicionar_pedido(
    *,
    tenant_id: TenantId,
    unidade_id: UnidadeId,
    pedido_id: PedidoId,
    destino: PedidoStatus,
    versao_esperada: int,
    idempotency_key: IdempotencyKey,
    contexto: ContextoExecucao,
    repositorio: RepositorioPedidos,
    outbox: PortaOutboxPedidos,
    auditoria: RepositorioAuditoria,
    timestamp: datetime,
    precondicoes: Mapping[str, bool] | None = None,
    motivo: str | None = None,
    decisao_cozinha: DecisaoCozinha | None = None,
    metadata: Mapping[str, object] | None = None,
) -> ResultadoPedidoAutoritativo:
    """Aplica exclusivamente uma transição permitida pela máquina normativa."""

    precondicoes_efetivas = dict(precondicoes or {})
    fingerprint = _fingerprint_transicao(
        destino=destino,
        versao_esperada=versao_esperada,
        motivo=motivo,
        precondicoes=precondicoes_efetivas,
    )
    metadata_efetiva = dict(metadata or {})
    metadata_efetiva[_REQUEST_FINGERPRINT_KEY] = fingerprint

    repetido = outbox.consultar(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        idempotency_key=idempotency_key,
    )
    if repetido is not None:
        fingerprint_persistido = repetido.payload.get(_REQUEST_FINGERPRINT_KEY)
        if (
            repetido.aggregate_id != str(pedido_id)
            or repetido.payload.get("destino") != destino.value
            or (
                fingerprint_persistido is not None
                and fingerprint_persistido != fingerprint
            )
        ):
            raise ConflitoIdempotencia("idempotency_key reutilizada em outra transição")
        atual = repositorio.buscar(tenant_id, unidade_id, pedido_id)
        if atual is None:
            raise RecursoNaoEncontrado("pedido não encontrado")
        return ResultadoPedidoAutoritativo(atual, repetido, None, True)

    atual = repositorio.buscar(tenant_id, unidade_id, pedido_id)
    if atual is None:
        raise RecursoNaoEncontrado("pedido não encontrado")
    _validar_contexto(atual, contexto)
    snapshot = SnapshotEstado(
        aggregate_type="pedido",
        aggregate_id=str(atual.id),
        tenant_id=str(atual.tenant_id),
        unidade_id=str(atual.unidade_id),
        estado=atual.status.value,
        version=atual.versao,
    )
    resultado = transicionar(
        snapshot,
        ComandoTransicao(
            destino=destino.value,
            versao_esperada=versao_esperada,
            idempotency_key=str(idempotency_key),
            timestamp=timestamp,
            contexto=contexto,
            precondicoes=precondicoes_efetivas,
            motivo=motivo,
            decisao_cozinha=decisao_cozinha,
            metadata=metadata_efetiva,
        ),
    )
    atualizado = replace(
        atual,
        status=PedidoStatus(resultado.snapshot.estado),
        atualizado_em=resultado.evento.timestamp,
        versao=resultado.snapshot.version,
    )
    persistido = repositorio.salvar(atualizado, versao_esperada=atual.versao)
    evento = EventoPedidoOperacional(
        event_id=EventoId(resultado.evento.event_id),
        aggregate_id=resultado.evento.aggregate_id,
        aggregate_type="pedido",
        tenant_id=TenantId(resultado.evento.tenant_id),
        unidade_id=UnidadeId(resultado.evento.unidade_id),
        correlation_id=CorrelationId(resultado.evento.correlation_id),
        causation_id=(
            CausationId(resultado.evento.causation_id)
            if resultado.evento.causation_id
            else None
        ),
        occurred_at=resultado.evento.timestamp,
        idempotency_key=IdempotencyKey(resultado.evento.idempotency_key),
        payload={
            "origem": atual.status.value,
            "destino": persistido.status.value,
            "aggregate_version": persistido.versao,
            **dict(resultado.evento.payload),
        },
        version=persistido.versao,
        tipo_evento=resultado.evento.event_type,
    )
    repositorio.salvar_eventos(
        persistido.tenant_id,
        persistido.unidade_id,
        persistido.id,
        (evento,),
    )
    envelope = _envelope(evento)
    outbox.adicionar(envelope)
    auditoria.adicionar(resultado.auditoria)
    return ResultadoPedidoAutoritativo(
        persistido, envelope, resultado.auditoria, resultado.idempotente
    )
