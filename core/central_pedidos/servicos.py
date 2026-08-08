"""Comandos da Central delegados a maquina de estados e repositorio de Pedido."""

from dataclasses import replace
from datetime import datetime, timezone
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
        repetido = self._session.scalar(
            select(EventoPedidoPersistidoORM).where(
                EventoPedidoPersistidoORM.tenant_id == contexto.tenant_id,
                EventoPedidoPersistidoORM.unidade_id == contexto.unidade_id,
                EventoPedidoPersistidoORM.pedido_id == pedido_id,
                EventoPedidoPersistidoORM.idempotency_key == idempotency_key,
            )
        )
        if repetido:
            if (
                repetido.version == versao_esperada + 1
                and repetido.event_type == f"pedido.{destino}"
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
            precondicoes or {},
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
                    payload=dict(resultado.evento.payload),
                    version=resultado.snapshot.version,
                )
            )
            self._session.flush()
        except Exception:
            self._session.rollback()
            raise
        self._auditoria.adicionar(resultado.auditoria)
        return atualizado
