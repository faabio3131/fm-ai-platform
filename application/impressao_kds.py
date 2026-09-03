"""Integração best-effort entre o fato canônico do KDS e o spool de impressão.

Esta camada nunca participa da transação do KDS. Ela lê somente dados já
persistidos e cria/deduplica o job em uma UoW própria de impressão.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from application.impressao_transacoes import AplicacaoImpressaoV1
from core.impressao import (
    DestinoImpressao,
    ErroImpressao,
    PortaImpressora,
    ResultadoEnfileiramento,
)
from core.kds import RepositorioKDSSQLAlchemy
from core.kds.modelos import ProducaoItem
from core.pedidos.modelos_orm import ItemPedidoORM
from core.seguranca.contexto import ContextoExecucao

SessionFactory = Callable[[], Session]


def _agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class IntegracaoImpressaoKDSV1:
    """Transforma roteamento KDS confirmado em job idempotente de impressão."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        impressora: PortaImpressora,
        destinos: tuple[DestinoImpressao, ...],
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._agora = agora or _agora_utc
        self._aplicacao = AplicacaoImpressaoV1(
            session_factory,
            impressora=impressora,
            destinos=destinos,
            agora=self._agora,
        )

    def enfileirar_roteamento(
        self,
        *,
        contexto: ContextoExecucao,
        producao: ProducaoItem,
        idempotency_key: str,
    ) -> ResultadoEnfileiramento:
        """Lê o KDS já commitado e grava somente o spool em transação separada."""

        with self._session_factory() as session:
            repositorio_kds = RepositorioKDSSQLAlchemy(session)
            setor = repositorio_kds.obter_setor(
                contexto.tenant_id,
                contexto.unidade_id,
                producao.setor_id,
            )
            if setor is None:
                raise ErroImpressao("setor_producao_indisponivel")

            item = session.scalar(
                select(ItemPedidoORM).where(
                    ItemPedidoORM.tenant_id == contexto.tenant_id,
                    ItemPedidoORM.unidade_id == contexto.unidade_id,
                    ItemPedidoORM.id == producao.pedido_item_id,
                    ItemPedidoORM.pedido_id == producao.pedido_id,
                )
            )
            if item is None:
                raise ErroImpressao("pedido_item_indisponivel")

            descricao_item = item.nome_produto
            observacao = item.observacao

        return self._aplicacao.enfileirar_item_kds(
            contexto=contexto,
            producao=producao,
            setor=setor,
            idempotency_key=f"kds-route:{idempotency_key}",
            descricao_item=descricao_item,
            observacao=observacao,
            timestamp=self._agora(),
        )
