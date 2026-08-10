"""Comandos da Central delegados a maquina de estados e repositorio de Pedido."""

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from json import dumps
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.ids import PedidoId, TenantId, UnidadeId
from core.estados.maquinas import (
    ComandoTransicao,
    ErroTransicao,
    SnapshotEstado,
    transicionar,
)
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.modelos_orm import EventoPedidoPersistidoORM
from core.seguranca.auditoria import EventoAuditoria, RepositorioAuditoria
from core.seguranca.contexto import ContextoExecucao

_IDEMPOTENCY_FINGERPRINT_KEY = "_central_idempotency_fingerprint"


def _fingerprint_transicao(
    *,
    pedido_id: str,
    destino: str,
    versao_esperada: int,
    motivo: str | None,
    precondicoes: dict[str, bool],
) -> str:
    payload = {
        "pedido_id": pedido_id,
        "destino": destino,
        "versao_esperada": versao_esperada,
        "motivo": motivo,
        "precondicoes": sorted(precondicoes.items()),
    }
    return sha256(
        dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class ServicoComandosCentral:
    def __init__(self, session: Session, auditoria: RepositorioAuditoria) -> None:
        self._session = session
        self._auditoria = auditoria

    def transicionar(
        self,
        *,
        contexto: ContextoExecucao,
        pedido_id: str,
        destino: str,
        versao_esperada: int,
        idempotency_key: str,
        motivo: str | None = None,
        timestamp: datetime | None = None,
        precondicoes: dict[str, bool] | None = None,
    ):
        repo = RepositorioPedidosSQLAlchemy(self._session)
        pedido = repo.buscar(
            TenantId(contexto.tenant_id),
            UnidadeId(contexto.unidade_id),
            PedidoId(pedido_id),
        )
        if pedido is None:
            raise LookupError("pedido_nao_encontrado")
        precondicoes_efetivas = precondicoes or {}
        fingerprint = _fingerprint_transicao(
            pedido_id=pedido_id,
            destino=destino,
            versao_esperada=versao_esperada,
            motivo=motivo,
            precondicoes=precondicoes_efetivas,
        )
        repetido = self._session.scalar(
            select(EventoPedidoPersistidoORM).where(
                EventoPedidoPersistidoORM.tenant_id == contexto.tenant_id,
                EventoPedidoPersistidoORM.unidade_id == contexto.unidade_id,
                EventoPedidoPersistidoORM.idempotency_key == idempotency_key,
            )
        )
        if repetido:
            fingerprint_persistido = dict(repetido.payload or {}).get(
                _IDEMPOTENCY_FINGERPRINT_KEY
            )
            if (
                repetido.pedido_id == pedido_id
                and fingerprint_persistido == fingerprint
            ):
                return pedido
            raise ValueError("conflito_idempotencia")
        snapshot = SnapshotEstado(
            "pedido",
            pedido_id,
            contexto.tenant_id,
            contexto.unidade_id,
            pedido.status.value,
            pedido.versao,
        )
        comando = ComandoTransicao(
            destino,
            versao_esperada,
            idempotency_key,
            timestamp or datetime.now(timezone.utc),
            contexto,
            precondicoes_efetivas,
            motivo,
        )
        try:
            resultado = transicionar(snapshot, comando)
        except ErroTransicao as erro:
            papel = next(iter(sorted(contexto.papeis, key=str)), None)
            self._auditoria.adicionar(
                EventoAuditoria(
                    str(uuid4()),
                    contexto.tenant_id,
                    contexto.unidade_id,
                    contexto.usuario_id,
                    papel,
                    f"pedido.{destino}",
                    "pedido",
                    pedido_id,
                    "negado",
                    erro.codigo,
                    contexto.correlation_id,
                    comando.timestamp,
                    contexto.origem,
                    "deny_by_default",
                    causation_id=contexto.causation_id,
                    antes_resumido=(("estado", snapshot.estado),),
                )
            )
            raise
        atualizado = replace(
            pedido,
            status=PedidoStatus(resultado.snapshot.estado),
            versao=resultado.snapshot.version,
            atualizado_em=resultado.evento.timestamp,
        )
        payload_evento = dict(resultado.evento.payload)
        payload_evento[_IDEMPOTENCY_FINGERPRINT_KEY] = fingerprint
        try:
            repo.salvar(atualizado, versao_esperada=versao_esperada)
            self._session.add(
                EventoPedidoPersistidoORM(
                    event_id=resultado.evento.event_id,
                    tenant_id=contexto.tenant_id,
                    unidade_id=contexto.unidade_id,
                    pedido_id=pedido_id,
                    event_type=resultado.evento.event_type,
                    correlation_id=contexto.correlation_id,
                    causation_id=contexto.causation_id,
                    idempotency_key=idempotency_key,
                    occurred_at=resultado.evento.timestamp,
                    payload=payload_evento,
                    version=resultado.snapshot.version,
                )
            )
            self._session.flush()
        except Exception:
            self._session.rollback()
            raise
        self._auditoria.adicionar(resultado.auditoria)
        return atualizado
