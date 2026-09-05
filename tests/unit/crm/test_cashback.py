from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.crm.cashback import MovimentoCashback, TipoMovimentoCashback
from core.crm.erros import ErroCRM


def _movimento(
    *, tipo: TipoMovimentoCashback = TipoMovimentoCashback.CREDITO, valor: str = "10.00"
) -> MovimentoCashback:
    return MovimentoCashback(
        movimento_id="cbmov-1",
        tenant_id="tenant-1",
        unidade_id="unidade-1",
        cliente_id="cliente-1",
        tipo=tipo,
        valor=Decimal(valor),
        origem="teste",
        referencia="pedido://1",
        ocorrido_em=datetime(2026, 9, 5, 20, 0, tzinfo=timezone.utc),
        idempotency_key="cashback-1",
    )


def test_movimento_cashback_normaliza_moeda_e_sinal() -> None:
    credito = _movimento(valor="10.005")
    debito = _movimento(tipo=TipoMovimentoCashback.DEBITO, valor="3.456")

    assert credito.valor == Decimal("10.01")
    assert credito.valor_assinado == Decimal("10.01")
    assert debito.valor == Decimal("3.46")
    assert debito.valor_assinado == Decimal("-3.46")


def test_movimento_cashback_exige_valor_positivo() -> None:
    with pytest.raises(ErroCRM, match="movimento_cashback_valor_invalido"):
        _movimento(valor="0")


def test_movimento_cashback_exige_timestamp_com_timezone() -> None:
    instante_sem_timezone = datetime.fromisoformat("2026-09-05T20:00:00")

    with pytest.raises(ErroCRM, match="timestamp_sem_timezone"):
        MovimentoCashback(
            movimento_id="cbmov-1",
            tenant_id="tenant-1",
            unidade_id="unidade-1",
            cliente_id="cliente-1",
            tipo=TipoMovimentoCashback.CREDITO,
            valor=Decimal(1),
            origem="teste",
            referencia="pedido://1",
            ocorrido_em=instante_sem_timezone,
            idempotency_key="cashback-1",
        )
