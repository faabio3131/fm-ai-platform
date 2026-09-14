"""Fronteira administrativa de leitura do Assistente de Atendimento V1.

Expõe consultas read-only para a superfície Web administrativa.
Reutiliza autoridades canônicas existentes sem duplicar lógica.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from core.assistente_atendimento.atendimento_adapters import PortaEstadoCanalAssistente
from core.assistente_atendimento.modelos import ConfiguracaoIdentidadeAssistente
from core.seguranca.contexto import ContextoExecucao
from infra.assistente_atendimento.canal_estado_sqlalchemy import (
    EncryptedSQLAlchemyChannelStateStore,
    EstadoCanalPersistido,
)
from infra.gerente_ia.persistencia_sqlalchemy import RepositorioIdentidadeAssistenteSQLAlchemy


class EstadoCanalLeitura:
    """DTO de leitura do estado do canal para a camada administrativa."""

    def __init__(self, estado: EstadoCanalPersistido) -> None:
        self.conversa_id = estado.conversa_id
        self.estado = estado.estado
        self.recipient = estado.recipient
        self.state = estado.state
        self.pedido_id = estado.pedido_id
        self.pagamento_id = estado.pagamento_id
        self.entrega_id = estado.entrega_id
        self.ultimo_inbound_id = estado.ultimo_inbound_id
        self.ultimo_outbound_id = estado.ultimo_outbound_id
        self.ultimo_status_hash = estado.ultimo_status_hash
        self.versao = estado.versao

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversa_id": self.conversa_id,
            "estado": self.estado,
            "recipient": self.recipient,
            "state": self.state,
            "pedido_id": self.pedido_id,
            "pagamento_id": self.pagamento_id,
            "entrega_id": self.entrega_id,
            "ultimo_inbound_id": self.ultimo_inbound_id,
            "ultimo_outbound_id": self.ultimo_outbound_id,
            "ultimo_status_hash": self.ultimo_status_hash,
            "versao": self.versao,
        }


class AssistenteAtendimentoAdmin:
    """Serviço administrativo de leitura do Assistente de Atendimento."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        canal_store: PortaEstadoCanalAssistente,
        identidade_repo: RepositorioIdentidadeAssistenteSQLAlchemy,
    ) -> None:
        self._session_factory = session_factory
        self._canal_store = canal_store
        self._identidade_repo = identidade_repo

    def obter_identidade(
        self,
        *,
        contexto: ContextoExecucao,
    ) -> ConfiguracaoIdentidadeAssistente:
        identidade = self._identidade_repo.obter(
            tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id
        )
        return identidade or ConfiguracaoIdentidadeAssistente.fallback(
            tenant_id=contexto.tenant_id, unidade_id=contexto.unidade_id
        )

    def obter_estado_canal(
        self,
        *,
        contexto: ContextoExecucao,
        conversa_id: str,
    ) -> EstadoCanalLeitura | None:
        estado = self._canal_store.obter_por_conversa(
            contexto=contexto, conversa_id=conversa_id
        )
        return EstadoCanalLeitura(estado) if estado is not None else None


def criar_assistente_atendimento_admin(
    *,
    session_factory: Callable[[], Session],
    master_key: str | None = None,
) -> AssistenteAtendimentoAdmin:
    """Factory para composição do serviço administrativo."""

    def _canal_store() -> PortaEstadoCanalAssistente:
        return EncryptedSQLAlchemyChannelStateStore(
            next(session_factory()), master_key=master_key
        )

    def _identidade_repo() -> RepositorioIdentidadeAssistenteSQLAlchemy:
        return RepositorioIdentidadeAssistenteSQLAlchemy(next(session_factory()))

    return AssistenteAtendimentoAdmin(
        session_factory=session_factory,
        canal_store=_canal_store(),
        identidade_repo=_identidade_repo(),
    )