"""Boundary transacional canônico de cashback aplicado pelo PDV."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.crm.cashback import ServicoCashback
from core.crm.erros import ErroCRM
from core.crm.modelos import moeda
from core.pdv.modelos import EntradaPDV
from infra.transacoes.uow import RecursosTransacionaisV1


class CashbackPDVInvalido(ErroCRM):
    pass


@dataclass(frozen=True)
class ResultadoCashbackPDV:
    cliente_id: str
    saldo: Decimal
    cashback_usado: Decimal
    cashback_ganho: Decimal


def aplicar_cashback_pdv_em_transacao(
    *,
    recursos: RecursosTransacionaisV1,
    tenant_id: str,
    unidade_id: str,
    pedido_id: str,
    entrada: EntradaPDV,
    timestamp: datetime,
) -> ResultadoCashbackPDV | None:
    """Aplica resgate/ganho no ledger sem possuir commit ou Session."""

    if entrada.cliente_id is None:
        return None

    vinculo = recursos.crm_cliente_legado.resolver(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        legacy_cliente_id=entrada.cliente_id,
    )
    if vinculo is None:
        raise CashbackPDVInvalido("cliente_legado_sem_mapping_crm")

    historico = recursos.cashback.historico(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        cliente_id=vinculo.cliente_id,
    )
    if not historico and vinculo.saldo_cashback_legado != Decimal("0.00"):
        raise CashbackPDVInvalido("cashback_legacy_regularizacao_pendente")

    servico = ServicoCashback(recursos.cashback)
    usado = moeda(entrada.desconto_cashback.valor) if entrada.usar_cashback else Decimal("0.00")
    ganho = moeda(entrada.total.valor * Decimal("0.05"))

    saldo = recursos.cashback.saldo(
        tenant_id=tenant_id,
        unidade_id=unidade_id,
        cliente_id=vinculo.cliente_id,
    )
    if usado > 0:
        resultado_debito = servico.debitar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=vinculo.cliente_id,
            valor=usado,
            origem="pdv_compra",
            referencia=pedido_id,
            idempotency_key=f"{entrada.idempotency_key}:cashback_use",
            ocorrido_em=timestamp,
        )
        saldo = resultado_debito.saldo

    if ganho > 0:
        resultado_credito = servico.creditar(
            tenant_id=tenant_id,
            unidade_id=unidade_id,
            cliente_id=vinculo.cliente_id,
            valor=ganho,
            origem="pdv_compra",
            referencia=pedido_id,
            idempotency_key=f"{entrada.idempotency_key}:cashback_gain",
            ocorrido_em=timestamp,
        )
        saldo = resultado_credito.saldo

    return ResultadoCashbackPDV(
        cliente_id=vinculo.cliente_id,
        saldo=saldo,
        cashback_usado=usado,
        cashback_ganho=ganho,
    )
