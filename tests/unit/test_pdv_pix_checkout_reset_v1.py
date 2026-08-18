from pdv_utils import (
    aplicar_reset_pendente_pdv,
    marcar_reset_pdv_apos_sucesso,
)


def test_reset_apos_venda_remove_todo_estado_pix_anterior():
    estado = {
        "pdv_checkout_id": "checkout-antigo",
        "pdv_pix_assinatura": "assinatura-antiga",
        "pdv_pix_provedor": "pagbank",
        "pdv_pix_id_externo": "cobranca-paga-antiga",
        "pdv_pix_status": "pago",
        "pdv_pix_copia_cola": "pix-antigo",
        "pdv_pix_qr_url": "https://example.invalid/qr",
        "pdv_pix_qr_base64": "base64-antigo",
        "pdv_pix_confirmado": True,
        "pdv_cliente_id": 123,
        "pdv_processando": True,
    }

    marcar_reset_pdv_apos_sucesso(estado, "Venda concluída")
    resetado = aplicar_reset_pendente_pdv(estado)

    assert resetado is True
    assert "pdv_checkout_id" not in estado
    assert "pdv_pix_assinatura" not in estado
    assert "pdv_pix_provedor" not in estado
    assert "pdv_pix_id_externo" not in estado
    assert "pdv_pix_status" not in estado
    assert "pdv_pix_copia_cola" not in estado
    assert "pdv_pix_qr_url" not in estado
    assert "pdv_pix_qr_base64" not in estado
    assert estado["pdv_pix_confirmado"] is False
    assert "pdv_cliente_id" not in estado
    assert estado["pdv_processando"] is False
