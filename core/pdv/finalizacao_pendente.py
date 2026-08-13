"""Persistencia do trabalho pendente para concluir PDV apos pagamento assincrono."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.dominio.dinheiro import Dinheiro

from .modelos import EntradaPDV
from .modelos_orm import FinalizacaoPendentePDVORM


_STATUS_PENDENTE = "PENDENTE"
_STATUS_FINALIZADA = "FINALIZADA"


def _payload_entrada(entrada: EntradaPDV) -> dict[str, object]:
    return {
        "produto_id": entrada.produto_id,
        "produto_nome": entrada.produto_nome,
        "quantidade": entrada.quantidade,
        "preco_unitario": str(entrada.preco_unitario.valor),
        "custo_total": str(entrada.custo_total.valor),
        "forma_pagamento": entrada.forma_pagamento,
        "terminal_id": entrada.terminal_id,
        "checkout_id": entrada.checkout_id,
        "cliente_id": entrada.cliente_id,
        "usar_cashback": entrada.usar_cashback,
        "desconto_cashback": str(entrada.desconto_cashback.valor),
    }


def reconstruir_entrada(row: FinalizacaoPendentePDVORM) -> EntradaPDV:
    payload = dict(row.payload)
    return EntradaPDV(
        produto_id=int(payload["produto_id"]),
        produto_nome=str(payload["produto_nome"]),
        quantidade=int(payload["quantidade"]),
        preco_unitario=Dinheiro(Decimal(str(payload["preco_unitario"]))),
        custo_total=Dinheiro(Decimal(str(payload["custo_total"]))),
        forma_pagamento=str(payload["forma_pagamento"]),
        terminal_id=str(payload["terminal_id"]),
        checkout_id=str(payload["checkout_id"]),
        cliente_id=(
            int(payload["cliente_id"]) if payload.get("cliente_id") is not None else None
        ),
        valor_recebido=None,
        usar_cashback=bool(payload.get("usar_cashback", False)),
        desconto_cashback=Dinheiro(Decimal(str(payload.get("desconto_cashback", "0")))),
        pix_sandbox=False,
        confirmacao_presencial=False,
    )


class RepositorioFinalizacaoPendentePDV:
    def __init__(self, session: Session) -> None:
        self.session = session

    def registrar(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pedido_id: str,
        pagamento_id: str,
        entrada: EntradaPDV,
        instante: datetime,
    ) -> FinalizacaoPendentePDVORM:
        existente = self.session.scalar(
            select(FinalizacaoPendentePDVORM).where(
                FinalizacaoPendentePDVORM.tenant_id == tenant_id,
                FinalizacaoPendentePDVORM.unidade_id == unidade_id,
                FinalizacaoPendentePDVORM.pagamento_id == pagamento_id,
            )
        )
        if existente is not None:
            if existente.pedido_id != pedido_id or existente.payload != _payload_entrada(entrada):
                raise RuntimeError("conflito_finalizacao_pdv")
            return existente

        chave = f"{entrada.idempotency_key}:finalizacao"
        row = FinalizacaoPendentePDVORM(
            id=str(uuid5(NAMESPACE_URL, f"{tenant_id}:{unidade_id}:{chave}")),
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            pedido_id=pedido_id,
            pagamento_id=pagamento_id,
            idempotency_key=chave,
            payload=_payload_entrada(entrada),
            status=_STATUS_PENDENTE,
            venda_financeira_id=None,
            venda_legada_id=None,
            criado_em=instante,
            finalizada_em=None,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def buscar_por_pagamento(
        self,
        *,
        tenant_id: str,
        unidade_id: str,
        pagamento_id: str,
        bloquear: bool = False,
    ) -> FinalizacaoPendentePDVORM | None:
        stmt = select(FinalizacaoPendentePDVORM).where(
            FinalizacaoPendentePDVORM.tenant_id == tenant_id,
            FinalizacaoPendentePDVORM.unidade_id == unidade_id,
            FinalizacaoPendentePDVORM.pagamento_id == pagamento_id,
        )
        if bloquear:
            stmt = stmt.with_for_update()
        return self.session.scalar(stmt)

    @staticmethod
    def finalizada(row: FinalizacaoPendentePDVORM) -> bool:
        return row.status == _STATUS_FINALIZADA

    def marcar_finalizada(
        self,
        row: FinalizacaoPendentePDVORM,
        *,
        venda_financeira_id: str,
        venda_legada_id: str,
        instante: datetime,
    ) -> None:
        row.status = _STATUS_FINALIZADA
        row.venda_financeira_id = venda_financeira_id
        row.venda_legada_id = venda_legada_id
        row.finalizada_em = instante
        self.session.flush()
