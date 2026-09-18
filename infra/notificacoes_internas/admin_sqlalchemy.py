"""Extensão de leitura administrativa sobre o diretório canônico de notificações."""

from __future__ import annotations

from sqlalchemy import select

from core.notificacoes_internas.modelos import DestinatarioNotificacaoInterna
from core.seguranca.contexto import ContextoExecucao

from .modelos_orm import DestinatarioNotificacaoInternaORM
from .repositorio_sqlalchemy import RepositorioNotificacoesInternasSQLAlchemy


class RepositorioNotificacoesInternasAdminSQLAlchemy(
    RepositorioNotificacoesInternasSQLAlchemy
):
    """Lista o diretório do escopo ativo sem expor material secreto."""

    def listar(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> tuple[DestinatarioNotificacaoInterna, ...]:
        rows = self._session.scalars(
            select(DestinatarioNotificacaoInternaORM)
            .where(
                DestinatarioNotificacaoInternaORM.tenant_id
                == contexto.tenant_id,
                DestinatarioNotificacaoInternaORM.unidade_id
                == contexto.unidade_id,
            )
            .order_by(
                DestinatarioNotificacaoInternaORM.nome_exibicao,
                DestinatarioNotificacaoInternaORM.destinatario_id,
            )
        ).all()
        return tuple(self._dominio(row) for row in rows)
