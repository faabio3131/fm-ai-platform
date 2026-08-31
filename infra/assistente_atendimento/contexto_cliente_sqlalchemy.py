"""Resolução governada de Customer Context para o Assistente V1."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from core.assistente_atendimento.customer_context import (
    ContextoClienteAutorizado,
    ItemHistoricoAtendimento,
    PedidoHistoricoAtendimento,
)
from core.pedidos.modelos_orm import PedidoORM
from core.seguranca.contexto import ContextoExecucao
from core.seguranca.permissoes import Permissao
from infra.crm.consentimentos_sqlalchemy import (
    RepositorioConsentimentosContextoSQLAlchemy,
)
from infra.crm.enderecos_sqlalchemy import EncryptedSQLAlchemyAddressStore
from infra.gerente_ia.persistencia_sqlalchemy import RepositorioClientesCRMSQLAlchemy


def _utc(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


class ContextoClienteAtendimentoSQLAlchemy:
    """Combina autoridades existentes sem criar memória livre ou acesso ad hoc."""

    def __init__(
        self,
        session: Session,
        *,
        master_key: str | None = None,
    ) -> None:
        self._session = session
        self._clientes = RepositorioClientesCRMSQLAlchemy(session)
        self._consentimentos = RepositorioConsentimentosContextoSQLAlchemy(session)
        self._enderecos = EncryptedSQLAlchemyAddressStore(
            session,
            master_key=master_key,
        )

    def resolver(
        self,
        *,
        contexto: ContextoExecucao,
        cliente_ref: str,
        limite_historico: int = 5,
    ) -> ContextoClienteAutorizado:
        if Permissao.CLIENTE_VISUALIZAR not in contexto.permissoes:
            raise PermissionError("cliente.visualizar obrigatoria")
        if not cliente_ref.strip():
            raise ValueError("cliente_contexto_obrigatorio")
        cliente = self._clientes.obter(
            tenant_id=contexto.tenant_id,
            unidade_id=contexto.unidade_id,
            cliente_id=cliente_ref,
        )
        if cliente is None:
            raise LookupError("cliente_contexto_indisponivel")

        rows = self._session.scalars(
            select(PedidoORM)
            .options(selectinload(PedidoORM.itens))
            .where(
                PedidoORM.tenant_id == contexto.tenant_id,
                PedidoORM.unidade_id == contexto.unidade_id,
                PedidoORM.cliente_id == cliente_ref,
                PedidoORM.status.in_(
                    (
                        "confirmado",
                        "enviado_producao",
                        "em_preparo",
                        "pronto",
                        "em_expedicao",
                        "saiu_entrega",
                        "servido",
                        "entregue",
                        "concluido",
                    )
                ),
            )
            .order_by(PedidoORM.criado_em.desc(), PedidoORM.id)
            .limit(max(1, min(limite_historico, 20)))
        ).all()

        historico = tuple(
            PedidoHistoricoAtendimento(
                pedido_id=row.id,
                status=row.status,
                criado_em=_utc(row.criado_em),
                total=Decimal(row.total),
                itens=tuple(
                    ItemHistoricoAtendimento(
                        produto_id=str(item.produto_id or ""),
                        nome_produto=item.nome_produto,
                        quantidade=item.quantidade,
                    )
                    for item in row.itens
                    if item.produto_id is not None
                ),
            )
            for row in rows
            if row.itens and all(item.produto_id is not None for item in row.itens)
        )

        return ContextoClienteAutorizado(
            cliente_ref=cliente_ref,
            historico=historico,
            consentimentos=self._consentimentos.atuais_cliente(
                tenant_id=contexto.tenant_id,
                unidade_id=contexto.unidade_id,
                cliente_id=cliente_ref,
            ),
            ultimo_endereco_ref=self._enderecos.ultimo_ref(
                contexto=contexto,
                cliente_id=cliente_ref,
            ),
        )
