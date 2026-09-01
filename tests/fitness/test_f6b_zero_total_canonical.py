from pathlib import Path


def test_f6b_remove_fallback_zero_para_legacy() -> None:
    source = Path("core/pdv/servicos.py").read_text(encoding="utf-8")
    assert "saldo_zero_financeiro_nao_modelado" not in source
    assert "modo = ModoPDV.LEGACY" not in source


def test_f6b_checkout_zero_nao_inventa_obrigacao() -> None:
    source = Path("core/pdv/cutover_canonico.py").read_text(encoding="utf-8")
    assert "exige_pagamento = entrada.total.valor > 0" in source
    assert "if exige_pagamento" in source


def test_f6b_zero_confirma_pedido_sem_venda_financeira() -> None:
    checkout = Path("application/checkout.py").read_text(encoding="utf-8")
    executor = Path("core/pdv/executor_canonico.py").read_text(encoding="utf-8")
    assert "confirmar_checkout_sem_obrigacao_financeira_em_transacao" in checkout
    assert "pdv_saldo_zero_com_obrigacao_financeira" in executor
    assert "venda_financeira_id=None" in executor
