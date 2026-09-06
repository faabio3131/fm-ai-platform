from pathlib import Path

APP = Path("app.py")
CRM_START = "# ABA 2: CRM E WHATSAPP"
PDV_START = "# ABA 3: FRENTE DE CAIXA"
PDV_END = "# ABA 4: ESTOQUE, ALMOXARIFADO & VALIDADES COM I.A."


def _trecho(source: str, inicio: str, fim: str) -> str:
    pos_inicio = source.find(inicio)
    pos_fim = source.find(fim, pos_inicio + len(inicio))
    assert pos_inicio >= 0, f"marcador ausente: {inicio}"
    assert pos_fim > pos_inicio, f"marcador ausente: {fim}"
    return source[pos_inicio:pos_fim]


def test_f13c_crm_nao_regride_para_cashback_legado_ou_fake_whatsapp() -> None:
    source = APP.read_text(encoding="utf-8")
    crm = _trecho(source, CRM_START, PDV_START)

    assert ".saldo_cashback" not in crm
    assert "mock_whatsapp_send" not in crm
    assert "_enviar_whatsapp_control_plane" not in crm
    assert "RuntimeCRMTeste" not in crm
    assert "runtime_teste" not in crm
    assert "creditar_cashback_manual" in crm
    assert "despachar_resgate_whatsapp_legado" in crm
    assert "_saldo_cashback_canonico_ui" in crm


def test_f13c_pdv_decide_cashback_somente_pela_autoridade_canonica() -> None:
    source = APP.read_text(encoding="utf-8")
    pdv = _trecho(source, PDV_START, PDV_END)

    assert ".saldo_cashback" not in pdv
    assert "_saldo_cashback_canonico_ui" in pdv
    assert "saldo_cashback_pdv" in pdv
    assert "saldo_cashback_banco" in pdv


def test_f13c_boundary_comercial_falha_fechado_sem_fallback_legado() -> None:
    cashback = Path("application/crm_cashback_comercial.py").read_text(
        encoding="utf-8"
    )
    marketing = Path("application/crm_marketing_comercial.py").read_text(
        encoding="utf-8"
    )

    assert "cashback_legacy_regularizacao_pendente" in cashback
    assert "cliente_legado_sem_mapping_crm" in cashback
    assert "cliente_legado_sem_mapping_crm" in marketing
    assert "CanalMarketing.WHATSAPP" in marketing
    assert "FinalidadeMarketing.PROMOCOES" in marketing
    assert "runtime_teste" not in marketing
    assert "EnvioMarketingFake" not in marketing
    assert "EnvioMarketingTeste" not in marketing
