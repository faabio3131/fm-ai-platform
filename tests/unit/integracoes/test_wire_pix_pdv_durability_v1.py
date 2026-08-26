from pathlib import Path

from scripts.wire_pix_pdv_durability_v1 import aplicar

APP_SOURCE = Path("app.py").read_text(encoding="utf-8")


def test_patch_liga_persistencia_recuperacao_e_confirmacao_duravel() -> None:
    atualizado = aplicar(APP_SOURCE)

    assert "registrar_vinculo_cobranca_pix(" in atualizado
    assert "recuperar_pix_aberto_por_terminal" in atualizado
    assert "confirmar_cobranca_pix_consultada(" in atualizado
    assert 'origem="app.pdv.pix_recovery"' in atualizado
    assert 'st.session_state["pdv_pix_pagamento_id"]' in atualizado
    assert "assinatura_checkout_duravel" in atualizado
    assert "terminal_pix_pdv" in atualizado


def test_patch_e_idempotente() -> None:
    primeira = aplicar(APP_SOURCE)
    segunda = aplicar(primeira)
    assert segunda == primeira

