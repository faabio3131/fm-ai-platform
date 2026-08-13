"""Unit of Work único para Pedido, Pagamento, Estoque, Eventos e Auditoria.

Todos os repositorios compartilham exatamente a mesma Session. O commit é explícito;
se qualquer efeito falhar, a saída do contexto faz rollback de tudo.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from core.estoque.adaptador_sqlalchemy import RepositorioLedgerSQLAlchemy
from core.pagamentos.adaptador_sqlalchemy import RepositorioPagamentosSQLAlchemy
from core.pedidos.adaptador_sqlalchemy import RepositorioPedidosSQLAlchemy
from infra.eventos.adaptador_sqlalchemy import (
    RepositorioDLQSQLAlchemy,
    RepositorioInboxSQLAlchemy,
    RepositorioOutboxSQLAlchemy,
)
from infra.seguranca.auditoria_sqlalchemy import RepositorioAuditoriaSQLAlchemy


class UnitOfWorkV1:
    """Fronteira transacional autoritativa da aplicação V1."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.committed = False

    def __enter__(self) -> UnitOfWorkV1:
        if self.session is not None:
            raise RuntimeError("UnitOfWorkV1 nao pode ser reutilizado enquanto aberto")
        self.session = self._session_factory()
        self.pedidos = RepositorioPedidosSQLAlchemy(self.session)
        self.pagamentos = RepositorioPagamentosSQLAlchemy(self.session)
        self.estoque = RepositorioLedgerSQLAlchemy(self.session)
        self.outbox = RepositorioOutboxSQLAlchemy(self.session)
        self.inbox = RepositorioInboxSQLAlchemy(self.session)
        self.dlq = RepositorioDLQSQLAlchemy(self.session)
        self.auditoria = RepositorioAuditoriaSQLAlchemy(self.session)
        self.committed = False
        return self

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWorkV1 nao iniciado")
        self.session.commit()
        self.committed = True

    def rollback(self) -> None:
        if self.session is not None:
            self.session.rollback()
        self.committed = False

    def flush(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWorkV1 nao iniciado")
        self.session.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        del exc, traceback
        if self.session is None:
            return False
        try:
            if exc_type is not None or not self.committed:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
        return False
