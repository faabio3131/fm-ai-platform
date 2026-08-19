from datetime import datetime, timezone

from infra.integracoes.mercado_pago_healthcheck import _evidencia
from scripts.wire_mercado_pago_access_healthcheck_v1 import aplicar


class _Contexto:
    tenant_id = "tenant-a"
    unidade_id = "unidade-a"


def test_evidencia_mercado_pago_e_sanitizada_e_deterministica() -> None:
    agora = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
    evidencia = _evidencia(
        contexto=_Contexto(),  # type: ignore[arg-type]
        configuracao_id="pagamentos.pix--mercado_pago",
        usuario_id="123456789",
        agora=agora,
    )
    assert evidencia.startswith(
        "healthcheck://mercado-pago-access/20260819T120000Z/"
    )
    assert "123456789" not in evidencia
    assert "token" not in evidencia.casefold()
    assert "secret" not in evidencia.casefold()


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


def test_patch_ui_deixa_claro_que_healthcheck_valida_credencial_e_pix_fica_pendente() -> None:
    origem = '''from infra.integracoes.meta_healthcheck import executar_healthcheck_meta\n\n        ultima_evidencia_meta = st.session_state.get(\n\n        if spec.provedor == "meta" and existing is not None:\n'''
    atualizado = aplicar(origem)
    assert "Access Token do Mercado Pago validado externamente" in atualizado
    assert "prova PIX transacional sandbox continua pendente" in atualizado
    assert "disponibilidade de PIX validados em modo somente leitura" not in atualizado


def test_patch_ui_migra_textos_antigos_sem_duplicar_bloco() -> None:
    origem = '''from infra.integracoes.mercado_pago_healthcheck import executar_healthcheck_mercado_pago\n
        ultima_evidencia_mp = st.session_state.get(
            _key(spec, "last_real_mercado_pago_access_evidence")
        )
        if spec.provedor == "mercado_pago" and ultima_evidencia_mp:
            st.success(
                "Acesso externo Mercado Pago e disponibilidade de PIX validados em modo somente leitura."
            )
            st.code(str(ultima_evidencia_mp), language=None)
            st.caption(
                "Esta evidência não criou pagamento nem movimentou dinheiro. A homologação final ainda exige criar um PIX controlado em ambiente de teste e validar status/webhook."
            )

        if spec.provedor == "mercado_pago" and existing is not None:
            st.caption(
                "Este healthcheck consulta de verdade os meios de pagamento disponíveis usando o Access Token salvo no cofre. É somente leitura: não cria PIX, não cobra ninguém e não homologa automaticamente."
            )
            if st.button(
                "Testar acesso real Mercado Pago (sem criar pagamento)",
                key=_key(spec, "real_mercado_pago_access_healthcheck"),
            ):
                _set_flash(
                    spec,
                    "success",
                    "Mercado Pago respondeu com sucesso e o PIX está disponível para a credencial configurada. Nenhum pagamento foi criado. A prova transacional controlada continua pendente.",
                )
                _set_flash(
                    spec,
                    "error",
                    "O healthcheck externo do Mercado Pago falhou. A integração continua não homologada; revise ambiente, Access Token e disponibilidade do PIX. Nenhum segredo foi exposto e nenhum pagamento foi criado.",
                )

        if spec.provedor == "meta" and existing is not None:
'''
    atualizado = aplicar(origem)
    assert atualizado.count("Testar acesso real Mercado Pago (sem criar pagamento)") == 1
    assert "Mercado Pago aceitou o Access Token salvo no cofre" in atualizado
    assert "revise ambiente e Access Token" in atualizado
    assert "disponibilidade do PIX" not in atualizado
