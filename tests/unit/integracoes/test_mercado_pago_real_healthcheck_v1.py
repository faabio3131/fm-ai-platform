from datetime import datetime, timezone

from infra.integracoes.mercado_pago_healthcheck import _evidencia, _pix_ativo
from scripts.wire_mercado_pago_access_healthcheck_v1 import aplicar


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_mercado_pago_e_sanitizada_e_deterministica() -> None:
    agora = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    evidencia = _evidencia(
        contexto=_Contexto(),  # type: ignore[arg-type]
        configuracao_id="pagamentos.pix--mercado_pago",
        quantidade_meios=8,
        agora=agora,
    )
    assert evidencia.startswith(
        "healthcheck://mercado-pago-access/20260819T120000Z/"
    )
    assert "token" not in evidencia.casefold()
    assert "secret" not in evidencia.casefold()


def test_pix_ativo_reconhece_id_pix() -> None:
    assert _pix_ativo({"id": "pix", "payment_type_id": "bank_transfer", "status": "active"})


def test_pix_ativo_reconhece_bank_transfer_brasil_mesmo_sem_nome_pix() -> None:
    assert _pix_ativo({"id": "bank_transfer", "payment_type_id": "bank_transfer", "name": "Transferência bancária", "status": "active"})


def test_pix_ativo_rejeita_meio_desativado() -> None:
    assert not _pix_ativo({"id": "pix", "payment_type_id": "bank_transfer", "status": "deactive"})


def test_patch_ui_adiciona_healthcheck_mp_sem_criar_pagamento_e_e_idempotente() -> None:
    origem = '''from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n\n        ultima_evidencia_meta = st.session_state.get(\n\n        if spec.provedor == "meta" and existing is not None:\n'''
    primeira = aplicar(origem)
    segunda = aplicar(primeira)
    assert primeira == segunda
    assert "executar_healthcheck_mercado_pago" in primeira
    assert "Testar acesso real Mercado Pago (sem criar pagamento)" in primeira
    assert "last_real_mercado_pago_access_evidence" in primeira
    assert "criar_pix(" not in primeira
    assert "registrar_homologacao" not in primeira


def test_patch_ui_deixa_claro_que_prova_transacional_continua_pendente() -> None:
    origem = '''from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n\n        ultima_evidencia_meta = st.session_state.get(\n\n        if spec.provedor == "meta" and existing is not None:\n'''
    atualizado = aplicar(origem)
    assert "Nenhum pagamento foi criado" in atualizado
    assert "prova transacional controlada continua pendente" in atualizado
