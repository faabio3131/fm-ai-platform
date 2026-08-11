"""Helpers exclusivos do runtime de teste da PR11."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from core.dominio.enums import PagamentoStatus
from core.pagamentos.modelos_orm import (
    ObrigacaoPagamentoORM,
    PagamentoORM,
    PaymentsBase,
)
from core.pedidos.modelos_orm import OrdersBase
from core.seguranca import MATRIZ_PADRAO, ContextoExecucao, Papel

from .flags import salao_v1_enabled
from .modelos_orm import SalaoBase


def preparar_schema_teste(engine: Any) -> None:
    if not salao_v1_enabled():
        raise RuntimeError("Schema Salao V1 so pode ser preparado em teste isolado")
    OrdersBase.metadata.create_all(engine, checkfirst=True)
    PaymentsBase.metadata.create_all(engine, checkfirst=True)
    SalaoBase.metadata.create_all(engine, checkfirst=True)


def contexto_salao_teste(
    *, correlation_id: str, solicitado_em: datetime, papel: str = "gerente"
) -> ContextoExecucao:
    if not salao_v1_enabled():
        raise RuntimeError("Contexto Salao E2E indisponivel")
    papel_efetivo = Papel(papel)
    return ContextoExecucao(
        "tenant-e2e",
        "unidade-e2e",
        f"{papel}-e2e",
        frozenset({papel_efetivo}),
        MATRIZ_PADRAO[papel_efetivo],
        correlation_id,
        solicitado_em,
        "salao-e2e",
        unidades_permitidas=frozenset({"unidade-e2e"}),
    )

def registrar_pagamento_confirmado_teste(
    session: Session,
    *,
    pagamento_id: str,
    pedido_id: str,
    comanda_id: str,
    metodo: str,
    valor: Decimal,
    agora: datetime,
) -> None:
    if not salao_v1_enabled():
        raise RuntimeError("Simulacao financeira Salao indisponivel fora de teste")
    if session.get(PagamentoORM, (pagamento_id, "tenant-e2e", "unidade-e2e")):
        return
    chave = f"salao-e2e:{pagamento_id}"
    session.add(
        ObrigacaoPagamentoORM(
            id=pagamento_id,
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=pedido_id,
            comanda_id=comanda_id,
            valor_previsto=valor,
            moeda="BRL",
            criado_em=agora,
            versao=1,
            correlation_id=str(uuid4()),
            idempotency_key=f"obrigacao:{chave}",
            request_hash=f"hash-obrigacao-{pagamento_id}",
        )
    )
    session.flush()
    session.add(
        PagamentoORM(
            id=pagamento_id,
            tenant_id="tenant-e2e",
            unidade_id="unidade-e2e",
            pedido_id=pedido_id,
            comanda_id=comanda_id,
            status=PagamentoStatus.PAGO.value,
            metodo=metodo,
            valor_previsto=valor,
            valor_pago=valor,
            valor_estornado=Decimal("0.00"),
            saldo=Decimal("0.00"),
            moeda="BRL",
            recebimento_posterior=False,
            provedor="salao-e2e",
            criado_em=agora,
            atualizado_em=agora,
            versao=1,
            correlation_id=str(uuid4()),
            idempotency_key=f"pagamento:{chave}",
            request_hash=f"hash-pagamento-{pagamento_id}",
        )
    )
    session.flush()

