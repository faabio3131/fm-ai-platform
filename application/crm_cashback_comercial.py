"""Boundary comercial de leitura e ajuste manual do cashback canônico.

O ledger CRM é a autoridade econômica. A coluna ``clientes.saldo_cashback``
permanece somente como projeção de compatibilidade para superfícies legadas que
ainda não passaram pelo cutover.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.crm.cashback import ServicoCashback
from core.crm.erros import ErroCRM
from core.crm.modelos import moeda
from infra.legacy_schema import clientes
from infra.transacoes.uow import RecursosTransacionaisV1, UnitOfWorkV1


class CashbackComercialInvalido(ErroCRM):
    """Falha fechada quando o legado não pode ser ligado à autoridade CRM."""


@dataclass(frozen=True)
class SaldoCashbackComercial:
    legacy_cliente_id: int
    cliente_id: str
    saldo: Decimal


def _resolver_vinculo(
    *,
    recursos: RecursosTransacionaisV1,
    tenant_id: str,
    unidade_id: str,
    legacy_cliente_id: int,
):
    vinculo = recursos.crm_cliente_legado.resolver(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        legacy_cliente_id=legacy_cliente_id,
    )
    if vinculo is None:
        raise CashbackComercialInvalido("cliente_legado_sem_mapping_crm")

    historico = recursos.cashback.historico(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        cliente_id=vinculo.cliente_id,
    )
    if not historico and vinculo.saldo_cashback_legado != Decimal("0.00"):
        raise CashbackComercialInvalido("cashback_legacy_regularizacao_pendente")
    return vinculo


def consultar_saldo_cashback_legado(
    *,
    session_factory: Callable[[], Session],
    tenant_id: str,
    unidade_id: str,
    legacy_cliente_id: int,
) -> SaldoCashbackComercial:
    """Consulta saldo somente no ledger, nunca na coluna legada."""

    with UnitOfWorkV1(session_factory) as uow:
        vinculo = _resolver_vinculo(
            recursos=uow.recursos,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            legacy_cliente_id=legacy_cliente_id,
        )
        saldo = uow.cashback.saldo(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=vinculo.cliente_id,
        )
        return SaldoCashbackComercial(
            legacy_cliente_id=legacy_cliente_id,
            cliente_id=vinculo.cliente_id,
            saldo=moeda(saldo),
        )


def creditar_cashback_manual(
    *,
    session_factory: Callable[[], Session],
    tenant_id: str,
    unidade_id: str,
    legacy_cliente_id: int,
    valor: Decimal,
    referencia: str,
    idempotency_key: str,
) -> SaldoCashbackComercial:
    """Credita ledger e atualiza a projeção legada na mesma transação."""

    valor = moeda(valor)
    if valor <= 0:
        raise CashbackComercialInvalido("cashback_manual_valor_invalido")
    if not referencia.strip() or not idempotency_key.strip():
        raise CashbackComercialInvalido("cashback_manual_referencia_invalida")

    with UnitOfWorkV1(session_factory) as uow:
        vinculo = _resolver_vinculo(
            recursos=uow.recursos,
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            legacy_cliente_id=legacy_cliente_id,
        )
        resultado = ServicoCashback(uow.cashback).creditar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=vinculo.cliente_id,
            valor=valor,
            origem="ajuste_manual_governado",
            referencia=referencia,
            idempotency_key=idempotency_key,
        )

        # Compatibilidade somente: replica o saldo final produzido pela autoridade.
        uow.session.execute(
            update(clientes)
            .where(clientes.c.id == legacy_cliente_id)
            .values(saldo_cashback=float(resultado.saldo))
        )
        uow.commit()
        return SaldoCashbackComercial(
            legacy_cliente_id=legacy_cliente_id,
            cliente_id=vinculo.cliente_id,
            saldo=moeda(resultado.saldo),
        )
