"""Comandos da Central delegados exclusivamente ao Pedido autoritativo V1.

A Central nao possui maquina de estados, historico ou idempotencia paralelos.
Pedido, historico, Outbox e auditoria sao gravados pela mesma transacao externa.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.dominio.enums import PedidoStatus
from core.dominio.ids import IdempotencyKey, PedidoId, TenantId, UnidadeId
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from core.pedidos.servicos import ResultadoPedidoAutoritativo, transicionar_pedido
from core.seguranca.auditoria import RepositorioAuditoria
from core.seguranca.contexto import ContextoExecucao
from infra.eventos.adaptador_sqlalchemy import RepositorioOutboxSQLAlchemy
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class ServicoComandosCentral:
    """Fachada fina da Central sobre o caso de uso canonico de Pedido."""

    def __init__(
        self,
        session: Session,
        auditoria: RepositorioAuditoria | None = None,
    ) -> None:
        self._session = session
        self._auditoria = auditoria or RepositorioAuditoriaSQLAlchemy(session)

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
        precondicoes: Mapping[str, bool] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> ResultadoPedidoAutoritativo:
        """Executa uma transicao sem criar uma segunda verdade operacional."""

        try:
            destino_canonico = PedidoStatus(destino)
        except ValueError as exc:
            raise ValueError("status_pedido_invalido") from exc

        return transicionar_pedido(
            tenant_id=TenantId(contexto.tenant_id),
            unidade_id=UnidadeId(contexto.unidade_id),
            pedido_id=PedidoId(pedido_id),
            destino=destino_canonico,
            versao_esperada=versao_esperada,
            idempotency_key=IdempotencyKey(idempotency_key),
            contexto=contexto,
            repositorio=RepositorioPedidosSQLAlchemy(self._session),
            outbox=RepositorioOutboxSQLAlchemy(self._session),
            auditoria=self._auditoria,
            timestamp=timestamp or datetime.now(timezone.utc),
            precondicoes=precondicoes,
            motivo=motivo,
            metadata=metadata,
        )
